
import threading
import logging
import socket

import signal
import time

import config
import sys
import json
import copy
from threading import Thread, Lock

# global variables
exit_me = False
query_thread_exited = False
convegence_reached = False
mutex = Lock()
num_client_exited = 0
network_state = {}

def log_me(msg):
    logging.info(msg)

def exit_gracefully(sig, frame):
    global exit_me
    log_me('You pressed Ctrl+C!')
    exit_me = True

def get_timeout():
    return 1

def decrement_num_client_exited():
    global mutex
    global  num_client_exited

    mutex.acquire()
    try:
        num_client_exited = num_client_exited - 1
    finally:
        mutex.release()

def send_update_client(config_obj, my_peer, network_state):

    global mutex
    global convegence_reached

    HOST = my_peer  # The server's hostname or IP address
    PORT = config_obj.get_port()  # The port used by the server

    log_me("Connecting to {}:{}".format(HOST, PORT))


    while True:

        last_time = False

        if convegence_reached:
            last_time = True

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.settimeout(get_timeout())
            s.connect((HOST, PORT))
            log_me("Connection to peer {} successful!!!".format(my_peer))

            send_payload = {}
            mutex.acquire()
            try :
                send_payload = json.dumps(network_state)
            finally:
                mutex.release()

            log_me("Sending {}".format(send_payload))
            s.sendall(send_payload)

            log_me("Network state pushed to peer {} successful!!!".format(my_peer))

            s.close()
            if last_time:
                log_me("Exiting client for peer {}".format(my_peer))
                decrement_num_client_exited()
                return
            time.sleep(get_timeout())
            continue
        except socket.timeout:
            log_me("Connection Timed out for {}".format(my_peer))
            if exit_me:
                break

            if last_time:
                log_me("Exiting client for peer {}".format(my_peer))
                decrement_num_client_exited()
                return

            continue
        except socket.error:
            log_me ("Couldnt connect with the socket-server: {} {} ".format(HOST, PORT))
            log_me("Convergence reached {}".format(convegence_reached))
            log_me("Last time {}".format(last_time))
            time.sleep(get_timeout())
            if exit_me:
                break

            if last_time:
                log_me("Exiting client for peer {}".format(my_peer))
                decrement_num_client_exited()
                return

            continue

    log_me("...Exiting client for peer {}".format(my_peer))
    decrement_num_client_exited()
    return

def check_convergence_achieved(network_state):

    for node in network_state["state"]:
        for my_neighbor in network_state["state"][node]["nodes"]:
            if my_neighbor not in network_state["state"]:
                return False
        if len(network_state["state"][node]["nodes"]) != network_state["state"][node]["num"]:
            return False

    return True

def merge_network_state(config_obj, data, network_state):
    global mutex
    global convegence_reached

    mutex.acquire()

    try:
        data_json_obj = json.loads(data)
        id = data_json_obj['id']

        # update my node state

        if id not in network_state["state"][config_obj.get_name()]["nodes"]:
            network_state["state"][config_obj.get_name()]["nodes"].append(id)

        # update other nodes in the network if there is information
        for id in data_json_obj["state"]:
            if id == config_obj.get_name():
                continue

            if id not in network_state["state"]:
                network_state["state"][id] = {}
                network_state["state"][id] = copy.deepcopy(data_json_obj["state"][id])
                continue

            for j in data_json_obj["state"][id]["nodes"]:
                if j not in network_state["state"][id]["nodes"]:
                    network_state["state"][id]["nodes"].append(j)


        #print (network_state)

        if check_convergence_achieved(network_state):
            log_me("Convergence achieved........")
            convegence_reached = True
        else:
            log_me("Convergence not achieved........")

    finally:
        mutex.release()

def print_final_network(network_state, output_file):

    log_me("===================")
    o = open(output_file, "w")
    for node in network_state["state"]:
        network_state["state"][node]["nodes"].sort()
        s = "{} : {}\n".format(node, ",".join(network_state["state"][node]["nodes"]))
        o.write(s)
        log_me(s)
    log_me("===================")
    o.close()

def update_server(config_obj, network_state):

    global exit_me
    global query_thread_exited


    logging.info("Thread %s: starting", config_obj.get_name())

    # Create a TCP/IP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Bind the socket to the port
    server_address = (config_obj.get_ip(), config_obj.get_port())
    msg = 'Starting query server up on %s port %s' % server_address
    log_me(msg)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(server_address)

    #sock.settimeout(get_timeout())

    # Listen for incoming connections
    sock.listen(1024)

    while exit_me == False:

        try:
            connection = None
            connection, client_address = sock.accept()
            #connection.settimeout(get_timeout())
            log_me('connection from {}'.format(client_address))

            data = connection.recv(1024)
            log_me('received "%s"' % data)
            if data:
                merge_network_state(config_obj, data, network_state)
            else:
                log_me('no more data from '.format(client_address))

            if convegence_reached:
                break

        except socket.timeout:
            log_me("Socket connection timed out !!")
            if exit_me:
                break
            continue

        except socket.error as msg:
            log_me("Socket connection ERROR !! {} {}".format(client_address, msg))
            time.sleep(get_timeout())
            if exit_me:
                return
            continue

        finally:
            # Clean up the connection
            if connection != None:
                log_me('Cleanup the connection on {}'.format(client_address))
                connection.close()

    sock.close()
    query_thread_exited = True
    logging.info("update_server thread %s: exiting", config_obj.get_name())


format = "%(asctime)s: %(message)s"
logging.basicConfig(format=format, level=logging.INFO, datefmt="%H:%M:%S")

# register signak handler
signal.signal(signal.SIGINT, exit_gracefully)

config_obj = config.config_read(sys.argv[1])

# start query server thread to answer our ID
q = threading.Thread(target=update_server, args=(config_obj, network_state))
q.start()

network_state["id"] = config_obj.get_name()
network_state["state"] = {}
network_state["state"][config_obj.get_name()] = { "nodes" : [], "num" : len(config_obj.get_neighbors())}


num_client_exited = len(config_obj.get_neighbors())

log_me("Number of clients to be exited {}".format(num_client_exited))
for i in config_obj.get_neighbors():
    # start update state server thread to answer our ID
    c = threading.Thread(target=send_update_client, args=(config_obj, i, network_state))
    c.start()


# keep serving other peers till program ended
while (convegence_reached == False and exit_me == False):
    time.sleep(1)

if exit_me:
    log_me("Program terminated by User!!")
    #sys.exit(1)
else:
    log_me ("CONVERGENCE ACHIEVED!!!")
#print (network_state)


while num_client_exited != 0:
    log_me("Some clients left to be exited {}".format(num_client_exited))
    time.sleep(1)

if exit_me == False:
    log_me ("All clients exited !!")
    print_final_network(network_state, sys.argv[2])

logging.info("Program Terminating!!")

sys.exit(0)
