FROM fedora
MAINTAINER Lars Kellogg-Stedman <lars@oddbit.com>

RUN yum -y install \
	python-netaddr \
	python-requests \
	python-setuptools \
	python-uuid \
	iproute \
	; yum clean all

COPY .git/refs/heads/master /commit
COPY . /src
RUN cd /src; python setup.py install

ENTRYPOINT ["/usr/bin/kiwi"]
CMD ["--help"]

