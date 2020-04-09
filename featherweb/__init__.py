import usocket as socket
import uselect as select

class FeatherWeb(object):
    m_Socket = None
    m_Routes = []


    def __init__(self, addr='0.0.0.0', port=80, maxQ=5):
        address = socket.getaddrinfo(addr, port)[0][-1]
        self.m_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.m_Socket.bind(address)
        self.m_Socket.listen(maxQ)
                

    def __del__(self):
        self.m_Socket.close()


    def route(self, url, **kwargs):
        def _route(f):
            self.m_Routes.append((url, f, kwargs))
            return f
        return _route


    def run(self, timeout=5000, callback=None, **kwargs):
        """ Run the request server forever.  If provided, a callback is fired with kwargs on the timeout interval.
            Returning False from timeout callback shall cause the request server to exit."""

        poller = select.poll()
        poller.register(self.m_Socket, select.POLLIN)

        while True:
            events = poller.poll(timeout)
            if not events and callback:
                if not callback(**kwargs):
                    break
                continue

            for fd, event in events:
                if event & select.POLLHUP or event & select.POLLERR:
                    poller.unregister(self.m_Socket)
                    raise Exception ("POLLHUP/POLLERR")

                if fd is not self.m_Socket or not event & select.POLLIN:
                    continue


                client, address = self.m_Socket.accept()
                try:
                    f = client.makefile('rwb', 0)
                    request = f.readline()
                    method, path, proto = request.decode().split()

                    # This may be dangerous for the ESP8266.  Request headers may be extensively large - a simple
                    # Request with lots of HTTP headers could cause OOM crash. Request headers may be 8-16KB!
                    headers = {}
                    while True:
                        line = f.readline()
                        if not line or line == b'\r\n':
                            break
                        k, v = line.split(b":", 1)
                        headers[k] = v.strip()

                    found = False
                    for e in self.m_Routes:
                        pattern = e[0]
                        handler = e[1]

                        if path == pattern:
                            found = True
                            break

                    if not found:
                        raise

                    handler(client)

                except Exception as e:
                    client.sendall('HTTP/1.0 404 NA\r\n\r\n')

                finally:
                    client.close()

class HTTPResponse():

    def __init__(self, client, content_type="text/html; charset=utf-8", status="200", headers=None):
        """ Utility object for HTTP request responses. """
        self.client = client
        client.sendall("HTTP/1.0 %s NA\r\n" % status)
        client.sendall("Content-Type: ")
        client.sendall(content_type)
        if not headers:
            client.sendall("\r\n\r\n")
        else:
            client.sendall("\r\n")
            if isinstance(headers, bytes) or isinstance(headers, str):
                client.sendall(headers)
            else:
                for k, v in headers.items():
                    client.sendall(k)
                    client.sendall(": ")
                    client.sendall(v)
                    client.sendall("\r\n")
            client.sendall("\r\n")


    def sendtext(self, response):
        """ Send a textual response. """
        self.client.sendall(response)


    def sendfile(self, filename, chunksize=128):
        """ Send a file in response, one chunk at a time.  Caller handles exceptions. """
        with open(filename, 'rb') as f:
            while True:
                data = f.read(128)
                if not data:
                    break
                self.client.sendall(data)
