import os
import select


def iter_lines(fd, chunk_size=1024):
    '''Iterates over the content of a file-like object line-by-line.'''

    poll = select.poll()
    poll.register(fd, select.POLLIN)
    pending = None
    eof = False

    while not eof:
        for fd,event in poll.poll():
            chunk = os.read(fd, chunk_size)
            if not chunk:
                eof = True
                break

            if pending is not None:
                chunk = pending + chunk
                pending = None

            lines = chunk.splitlines()

            if lines and lines[-1]:
                pending = lines.pop()

            for line in lines:
                yield line

    if pending:
        yield(pending)
