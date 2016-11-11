from twisted.internet.defer import gatherResults
from twisted.logger import Logger, LogLevel

from marathon_acme.server import HealthServer
from marathon_acme.acme_util import create_txacme_service


def parse_domain_label(domain_label):
    """ Parse the list of comma-separated domains from the app label. """
    domains = []
    for domain_string in domain_label.split(','):
        domain = domain_string.strip()
        if domain:
            domains.append(domain)
    return domains


class MarathonAcme(object):
    log = Logger()

    def __init__(self, marathon_client, group, cert_store, mlb_client,
                 txacme_client_creator, reactor, txacme_client_pool=None):
        """
        Create the marathon-acme service.

        :param marathon_client: The Marathon API client.
        :param group: The name of the marathon-lb group.
        :param cert_store: The ``ICertificateStore`` instance to use.
        :param mlb_clinet: The marathon-lb API client.
        :param txacme_client_creator: Callable to create the txacme client.
        :param reactor: The reactor to use.
        :param txacme_client_pool: The txacme client's ``HTTPConnectionPool``.
        """
        self.marathon_client = marathon_client
        self.group = group
        self.reactor = reactor

        self.server = HealthServer()

        root_resource = self.server.app.resource()
        self.txacme_service = create_txacme_service(
            cert_store, mlb_client, txacme_client_creator, self.reactor,
            root_resource)

        self._server_listening = None
        self._txacme_client_pool = txacme_client_pool

    def run(self, host, port):
        # Start the server
        self._server_listening = self.server.listen(host, port, self.reactor)

        # Start the txacme service and wait for the initial check
        self.txacme_service.startService()
        d = self.txacme_service.when_certs_valid()

        # Run an initial sync
        d.addCallback(lambda _: self.sync())

        # Then listen for events...
        d.addCallback(lambda _: self.listen_events())

        # If anything goes wrong or listening for events returns, stop
        d.addBoth(self._stop)

        return d

    def _log_failure(self, failure, message):
        self.log.failure(message, failure)
        return failure

    def _stop(self, ignored):
        deferreds = [
            self._server_listening.stopListening(),
            self.txacme_service.stopService()
        ]
        if self._txacme_client_pool is not None:
            deferreds.append(self._txacme_client_pool.closeCachedConnections())

        return gatherResults(deferreds, consumeErrors=True)

    def listen_events(self):
        """
        Start listening for events from Marathon, triggering a sync on relevant
        events.
        """
        self.log.info('Listening for events from Marathon...')

        def on_finished(result):
            raise RuntimeError('Connection lost listening for events')

        def log_failure(failure):
            self.log.failure('Failed to listen for events', failure)
            return failure

        return self.marathon_client.get_events({
            'api_post_event': self._sync_on_event
        }).addCallbacks(on_finished, log_failure)

    def _sync_on_event(self, event):
        self.log.info('Sync triggered by event with timestamp "{timestamp}"',
                      timestamp=event['timestamp'])
        return self.sync()

    def sync(self):
        """
        Fetch the list of apps from Marathon, find the domains that require
        certificates, and issue certificates for any domains that don't already
        have a certificate.
        """
        self.log.info('Starting a sync...')

        def log_success(result):
            self.log.info('Sync completed successfully')
            return result

        def log_failure(failure):
            self.log.failure('Sync failed', failure, LogLevel.error)
            return failure

        return (self.marathon_client.get_apps()
                .addCallback(self._apps_acme_domains)
                .addCallback(self._filter_new_domains)
                .addCallback(self._issue_certs)
                .addCallbacks(log_success, log_failure))

    def _apps_acme_domains(self, apps):
        domains = []
        for app in apps:
            domains.extend(self._app_acme_domains(app))

        self.log.debug('Found {len_domains} domains for apps: {domains}',
                       len_domains=len(domains), domains=domains)

        return domains

    def _app_acme_domains(self, app):
        app_domains = []
        labels = app['labels']
        app_group = labels.get('HAPROXY_GROUP')

        # Iterate through the ports, checking for corresponding labels
        for port_index, _ in enumerate(app['portDefinitions']):
            # Get the port group label, defaulting to the app group label
            port_group = labels.get(
                'HAPROXY_%d_GROUP' % (port_index,), app_group)

            if port_group == self.group:
                domain_label = labels.get(
                    'MARATHON_ACME_%d_DOMAIN' % (port_index,), '')
                port_domains = parse_domain_label(domain_label)

                if port_domains:
                    # TODO: Support SANs- for now just use the first domain
                    if len(port_domains) > 1:
                        self.log.warn(
                            'Multiple domains found for port {port} of app '
                            '{app}, only the first will be used',
                            port=port_index, app=app['id'])

                    app_domains.append(port_domains[0])

        self.log.debug(
            'Found {len_domains} domains for app {app}: {domains}',
            len_domains=len(app_domains), app=app['id'], domains=app_domains)

        return app_domains

    def _filter_new_domains(self, marathon_domains):
        def filter_domains(stored_domains):
            return set(marathon_domains) - set(stored_domains.keys())

        d = self.txacme_service.cert_store.as_dict()
        d.addCallback(filter_domains)
        return d

    def _issue_certs(self, domains):
        if domains:
            self.log.info(
                'Issuing certificates for {len_domains} domains: {domains}',
                len_domains=len(domains), domains=domains)
        else:
            self.log.debug('No new domains to issue certificates for')
        return gatherResults(
            [self.txacme_service.issue_cert(domain) for domain in domains])
