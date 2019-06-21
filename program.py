
import threading
import logging
import socket

import signal
import time

import config
import sys

exit_me = False
query_thread_exited = False

def log_me(msg):
    logging.info(msg)

def exit_gracefully(sig, frame):
    global exit_me
    log_me('You pressed Ctrl+C!')
    exit_me = True

def is_peer_db_filled(peers_db):
    for p in peers_db:
        if peers_db[p] == None:
            return False

    return True

my_peers = set()

def query_client(config_obj, my_peer):

    HOST = my_peer  # The server's hostname or IP address
    PORT = config_obj.get_port()  # The port used by the server

    log_me("Connecting to {}:{}".format(HOST, PORT))

    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((HOST, PORT))
            s.sendall(config_obj.get_name())
            s.close()
            return
        except socket.timeout:
            log_me("Connection Timed out for {}".format(my_peer))
            if exit_me:
                return
            continue
        except socket.error:
            log_me ("Couldnt connect with the socket-server: {} {} ".format(HOST, PORT))
            time.sleep(5)
            if exit_me:
                return
            continue

def query_server(config_obj):
    global exit_me
    global query_thread_exited

    logging.info("Thread %s: starting", config_obj.get_name())

    # Create a TCP/IP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Bind the socket to the port
    server_address = (config_obj.get_ip(), config_obj.get_port())
    msg = 'Starting query server up on %s port %s' % server_address
    log_me(msg)
    sock.bind(server_address)

    sock.settimeout(5)

    # Listen for incoming connections
    sock.listen(5)

    while exit_me == False:
        # Wait for a connection
        #log_me('waiting for a connection')

        try:
            connection = None
            connection, client_address = sock.accept()

            log_me('connection from {}'.format(client_address))

            data = connection.recv(16)
            log_me('received "%s"' % data)
            if data:
                my_peers.add(data)
            else:
                log_me('no more data from '.format(client_address))


        except socket.timeout:
            if exit_me:
                break
            else:
                continue

        finally:
            # Clean up the connection
            if connection != None:
                log_me('Cleanup the connection on {}'.format(client_address))
                connection.close()

    sock.close()
    query_thread_exited = True
    logging.info("Thread %s: exiting", config_obj.get_name())


format = "%(asctime)s: %(message)s"
logging.basicConfig(format=format, level=logging.INFO, datefmt="%H:%M:%S")

signal.signal(signal.SIGINT, exit_gracefully)


config_obj = config.config_read(sys.argv[1])

# start query server thread to answer our ID
q = threading.Thread(target=query_server, args=(config_obj,))
q.start()


for i in config_obj.get_neighbors():
    # start query server thread to answer our ID
    c = threading.Thread(target=query_client, args=(config_obj, i))
    c.start()


# keep serving other peers till program ended
while (query_thread_exited == False):
    print(config_obj.get_name() + " : [ " + ",".join(my_peers) + " ]")
    time.sleep(1)

logging.info("Program Terminating!!")

