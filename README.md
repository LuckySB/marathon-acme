# marathon-acme
Automate [ACME](https://en.wikipedia.org/wiki/Automated_Certificate_Management_Environment) certificates for [Marathon](https://mesosphere.github.io/marathon/) apps served by [`marathon-lb`](https://github.com/mesosphere/marathon-lb)

## How it works
There is one big requirement for deploying `marathon-acme`: there must be shared persistent storage between `marathon-acme` and all `marathon-lb` instances. This will be used to store the certificates.

 1. `marathon-acme` watches Marathon for changes to app definitions.
 2. It collects the values of all `MARATHON_ACME_{n}_DOMAIN` labels on apps. This will form the set of domains to fetch certificates for.
 3. It generates, verifies and stores certificates for any new domains using the configured ACME certificate authority.
 4. It tells `marathon-lb` to reload using the `marathon-lb` HTTP API.
 5. It issues new certificates for soon-to-expire certificates once a day.

`marathon-acme` is written in Python using [Twisted](https://twistedmatrix.com/trac/). The certificate issuing functionality is possible thanks to the [`txacme`](https://github.com/mithrandi/txacme) library.

The ACME provider that most people are likely to use is [Let's Encrypt](https://letsencrypt.org/). Before using `marathon-acme` with Let's Encrypt, make sure you are aware of their [rate limits](https://letsencrypt.org/docs/rate-limits/).

## Usage
`marathon-acme` will eventually be available as a pip-installable Python package on PyPi. For now, a development Docker image is available [here](https://hub.docker.com/r/praekeltfoundation/marathon-acme/).

```
> $ docker run --rm praekeltfoundation/marathon-acme:develop marathon-acme --help
usage: marathon-acme [-h] [-a ACME] [-m MARATHON] [-l LB [LB ...]] [-g GROUP]
                     [--listen LISTEN]
                     [--log-level {debug,info,warn,error,critical}]
                     storage-dir

Automatically manage ACME certificates for Marathon apps

positional arguments:
  storage-dir           Path to directory for storing certificates

optional arguments:
  -h, --help            show this help message and exit
  -a ACME, --acme ACME  The address for the ACME Directory Resource (default:
                        https://acme-v01.api.letsencrypt.org/directory)
  -m MARATHON, --marathon MARATHON
                        The address for the Marathon HTTP API (default:
                        http://marathon.mesos:8080)
  -l LB [LB ...], --lb LB [LB ...]
                        The address for the marathon-lb HTTP API (default:
                        http://marathon-lb.marathon.mesos:9090)
  -g GROUP, --group GROUP
                        The marathon-lb group to issue certificates for
                        (default: external)
  --listen LISTEN       The address for the port to listen on (default:
                        0.0.0.0:8000)
  --log-level {debug,info,warn,error,critical}
                        The minimum severity level to log messages at
                        (default: info)
```

### `marathon-acme` app definition
`marathon-acme` should be deployed as a Marathon app.

```json
{
  "id": "/marathon-acme",
  "cpus": 0.01,
  "mem": 128.0,
  "labels": {
    "HAPROXY_GROUP": "external",
    "HAPROXY_0_VHOST": "example.com",
    "HAPROXY_0_BACKEND_WEIGHT": "1",
    "HAPROXY_0_PATH": "/.well-known/acme-challenge/",
    "HAPROXY_0_HTTP_FRONTEND_ACL_WITH_PATH": "  acl path_{backend} path_beg {path}\n  use_backend {backend} if path_{backend}\n",
    "HAPROXY_0_HTTPS_FRONTEND_ACL_WITH_PATH": "  use_backend {backend} if path_{backend}\n"
  },
  "container": {
    "type": "DOCKER",
    "docker": {
      "image": "praekeltfoundation/marathon-acme:develop",
      "network": "BRIDGE",
      "portMappings": [
        { "containerPort": 8000, "hostPort": 0 }
      ],
      "parameters": [
        {
          "value": "xylem",
          "key": "volume-driver"
        },
        {
          "value": "marathon-acme-certs:/var/lib/marathon-acme",
          "key": "volume"
        }
      ],
    }
  }
}
```
The above should mostly be standard across different deployments. The volume parameters will depend on your particular networked storage solution.

#### `HAPROXY` labels
Several special `marathon-lb` labels are needed in order to forward all HTTP requests whose path begins with `/.well-known/acme-challenge/` to `marathon-acme`, in order to serve ACME [HTTP challenge](https://ietf-wg-acme.github.io/acme/#rfc.section.7.2) responses.

##### `HAPROXY_GROUP`
`marathon-lb` instances are assigned a group. Only Marathon apps with a `HAPROXY_GROUP` label that matches their group are routed with that instance. "external" is the common name for publicly-facing load balancers.

##### `HAPROXY_0_VHOST`
`marathon-lb` is designed with the assumption that things have domains. `marathon-acme` doesn't technically need one, but if we don’t specify this label, the app is not exposed to the outside world. Any value will do here, since we change the templates to never include this value.

##### `HAPROXY_0_BACKEND_WEIGHT`
We want this rule in HAProxy's config file to come before any others so that requests are routed to `marathon-acme` before we do the (usually) domain-based routing for the other Marathon apps. The default weight is `0`, so we set to `1` so that the rule comes first.

##### `HAPROXY_0_PATH`
This is the beginning of the HTTP path to ACME validation challenges.

##### `HAPROXY_0_HTTP_FRONTEND_ACL_WITH_PATH`
This is where it gets complicated... It’s possible to edit the templates used for generating the HAProxy on a per-app basis using labels. This is necessary because by default `marathon-lb` will route based on domain first, but we don’t want to do that. You can see the standard template [here](https://github.com/mesosphere/marathon-lb/blob/master/Longhelp.md#haproxy_http_frontend_acl_with_path). We simply remove the first line containing the hostname ACL.

##### `HAPROXY_0_HTTPS_FRONTEND_ACL_WITH_PATH`
`marathon-lb` exposes apps via port 443/HTTPS by default and there doesn’t seem to be a way to switch it off. We change the ACL template here so that HAProxy doesn’t try to do an SNI match on the hostname. The ACME Simple HTTP spec allows for challenges to occur over HTTPS if the client requests as such and will ignore the certificate presented on our side.

#### Environment variables
The `marathon-acme` Docker container can be configured either using command-line options (by setting the app definition's `args` field) or by environment variables (by setting the app definition's `env` field).

The environment variables available correspond to the CLI options as follows:

| Environment variable      | CLI option    |
|---------------------------|---------------|
| `MARATHON_ACME_ACME`      | `--acme`      |
| `MARATHON_ACME_MARATHON`  | `--marathon`  |
| `MARATHON_ACME_LBS`*      | `--lb`        |
| `MARATHON_ACME_GROUP`     | `--group`     |
| `MARATHON_ACME_LOG_LEVEL` | `--log-level` |

\*Multiple load balancers can be set using multiple spaces-separated addresses.

#### Volumes and ports
The `marathon-acme` container defaults to the `/var/lib/marathon-acme` directory to store certificates and the ACME client private key. This is the path inside the container that should be mounted as a shared volume.

The container also defaults to listening on port 8000 on all interfaces.

To override these values you must provide a custom command to the Docker container.

### `marathon-lb` configuration
`marathon-acme` requires `marathon-lb` 1.4.0 or later in order to be able to trigger HAProxy reloads.

As mentioned earlier, `marathon-lb` must share persistent storage with `marathon-acme`. BYONS: _bring your own networked storage._

The only real configuration needed for `marathon-lb` is to add the path to `marathon-acme`'s certificate storage directory as a source of certificates. HAProxy supports loading certificates from a directory. You should set `marathon-lb`'s `--ssl-certs` CLI option to the certificate directory path.

### App configuration
`marathon-acme` uses a single `marathon-lb`-like label to assign domains to app ports: `MARATHON_ACME_{n}_DOMAIN`, where `{n}` is the port index. The value of the label is a set of comma-separated domain names, although currently only the first domain name will be considered.

The app or its port must must be in the same `HAPROXY_GROUP` as `marathon-acme` was configured with at start-up.

We decided not to reuse the `HAPROXY_{n}_VHOST` label so as to limit the number of domains that certificates are issued for.

## Limitations
The current biggest limitation with `marathon-acme` is that it will only issue one certificate for one domain per app port. This is to limit the number of certificates issued so as to prevent hitting Let's Encrypt rate limits.

The library used for ACME certificate management, `txacme`, is currently quite limited in its functionality. The two biggest limitations are:
* Only anonymous ACME registrations are supported ([#72](https://github.com/mithrandi/txacme/issues/72)). This means you will not receive reminder emails from Let's Encrypt when your certificates are about to expire.
* There is no [Subject Alternative Name](https://en.wikipedia.org/wiki/Subject_Alternative_Name) (SAN) support yet ([#37](https://github.com/mithrandi/txacme/issues/37)). Each certificate will correspond to exactly one domain name. This limitation makes it easier to hit Let's Encrypt's rate limits.

For a more complete list of issues, see the issues page for this repo.
