import json

from klein import Klein
from twisted.logger import Logger
from twisted.web.http import OK, NOT_IMPLEMENTED, SERVICE_UNAVAILABLE
from twisted.web.server import Site


def write_request_json(request, json_obj):
    request.setHeader('Content-Type', 'application/json')
    request.write(json.dumps(json_obj).encode('utf-8'))


class HealthServer(object):

    app = Klein()
    health_handler = None
    log = Logger()

    def set_health_handler(self, health_handler):
        """
        Set the handler for the health endpoint.

        :param health_handler:
            The handler for health status requests. This must be a callable
            that returns a Health object.
        """
        self.health_handler = health_handler

    def listen(self, host, port, clock):
        """
        Run the server, i.e. start listening for requests on the given host and
        port.

        :param host: The address for the interface to listen on.
        :param port: The port to bind to.
        :param clock: The ``IReactorTCP`` to use.
        :return: An object that provides ``IListeningPort``.
        """
        site = Site(self.app.resource())
        return clock.listenTCP(port, site, interface=host)

    @app.route('/health', methods=['GET'])
    def health(self, request):
        """
        Listens to incoming pings from Marathon on ``/health``.

        :param klein.app.KleinRequest request:
            The Klein HTTP request
        """
        if self.health_handler is None:
            return self._no_health_handler(request)

        health = self.health_handler()
        response_code = OK if health.healthy else SERVICE_UNAVAILABLE
        request.setResponseCode(response_code)
        write_request_json(request, health.json_message)

    def _no_health_handler(self, request):
        self.log.warn('Request to /health made but no handler is set')
        request.setResponseCode(NOT_IMPLEMENTED)
        write_request_json(request, {
            'error': 'Cannot determine service health: no handler set'
        })


class Health(object):
    def __init__(self, healthy, json_message={}):
        """
        Health objects store the current health status of the service.

        :param bool healthy:
            The service is either healthy (True) or unhealthy (False).
        :param json_message:
            An object that can be serialized as JSON that will be sent as a
            message when the health status is requested.
        """
        self.healthy = healthy
        self.json_message = json_message
