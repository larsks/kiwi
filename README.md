# Kiwi, the Kubernetes IP Manager

This is a simple service for managing the assignment of IP addresses
to network interfaces and the associated firewall rules for Kubernetes
services.

The `kiwi` service will listen for notifications from the
Kubernetes API regarding new or deleted services, and for those that
contain a `publicIPs` element the service will:

- Associate the public ip with a network interface, if it has not
  already been assigned,
- Create `mangle` table rules to mark inbound traffic

Kiwi uses etcd to coordinate assignments between multiple systems.  If
Kiwi stops running on one system, any active ip addresses will be
assigned on the remaining systems.

## Using Kiwi

The easiest way to use Kiwi is to use the docker image:

    docker run --privileged --net=host larsks/kiwi --interface br0 --verbose

Kiwi needs `--net=host` and `--privileged` because it will be
modifying your host iptables and network interface configuration.

## Example

Assume that you have a Kubernetes service definition like this:

    kind: Service
    id: web
    apiVersion: v1beta1
    port: 8080
    selector:
      name: web
    containerPort: 80
    publicIps:
      - 192.168.1.41
      - 172.16.1.41

If you run `kiwi` like this:

    kiwi --interface em1 -r 192.168.1.0/24

And then create the Kubernetes services:

    kubectl create -f web-service.yaml

Then `kiwi` will:

- Add address 192.168.1.42/32 to device `em1`:

        # ip addr show em1 | grep 192.168.1.41
        inet 192.168.1.41/32 scope global em1:kube

- Add the following rule to the `mangle` `KUBE-PUBLIC`
  table:

        -A KUBE-PUBLIC -d 192.168.1.41/32 -p tcp -m tcp --dport 8080 -m comment --comment web -j MARK --set-mark 1

- Kiwi will ignore `172.16.1.41` because it does not match any valid
  CIDR range.

These changes will be removed if you delete the service.

When `kiwi` exits, it will remove any addresses and firewall rules it
created while it was running.

## Technical details

Kiwi works by listening to the Kubernetes API at
`/api/v1beta1/watch/services`.  As new services appear, Kiwi iterates
over the list of ip addresses and attempts to create corresponding
keys under the etcd prefix `/kiwi/publicips`.

If it is able to successfully create an entry, the local Kiwi agent
has "claimed" that address and will provision it locally.

Addresses are set with a TTL (10 seconds by default).  The local kiwi
agent will heartbeat on that address entry while it is running.  If
the local agent stops running, the `/kiwi/publicips/x.x.x.x` entry
will eventually expire, at which point another agent will attempt to
claim.

