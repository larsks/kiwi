# Kubernetes IP Manager

This is a simple service for managing the assignment of IP addresses
to network interfaces and the associated firewall rules for Kubernetes
services.

The `kube-ip-manager` service will listen for notifications from the
Kubernetes API regarding new or deleted services, and for those that
contain a `publicIPs` element the service will:

- Associate the public ip with a network interface, if it has not
  already been assigned,
- Create `mangle` table rules to mark inbound traffic

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

If you run `kube-ip-manager` like this:

    kube-ip-manager --interface em1

And then create the Kubernetes services:

    kubectl create -f web-service.yaml

Then `kube-ip-manager` will:

- Add address 192.168.1.42/32 to device `em1`:

        # ip addr show em1 | grep 192.168.1.41
        inet 192.168.1.41/32 scope global em1:kube

- Add the following rule to the `mangle` `KUBE-PUBLIC`
  table:

        -A KUBE-PUBLIC -d 192.168.1.41/32 -p tcp -m tcp --dport 8080 -m comment --comment web -j MARK --set-mark 1

These changes will be removed if you delete the service.

When `kube-ip-manager` exits, it will remove any addresses and
firewall rules it created while it was running.

