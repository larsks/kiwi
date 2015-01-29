FROM fedora

RUN yum -y install \
	python-netaddr \
	python-requests \
	python-setuptools \
	python-uuid \
	iproute \
	; yum clean all

RUN yum -y install \
	git \
	; yum clean all

RUN git clone -b cluster http://github.com/larsks/kube-ip-manager; \
	cd kube-ip-manager; \
	python setup.py install

ENTRYPOINT ["/usr/bin/kiwi"]
CMD ["--help"]

