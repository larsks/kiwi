FROM fedora

RUN yum -y install \
	python-netaddr \
	python-requests \
	python-setuptools \
	python-uuid \
	iproute \
	; yum clean all

COPY . /src
RUN cd /src; python setup.py install

ENTRYPOINT ["/usr/bin/kiwi"]
CMD ["--help"]

