# SDN based QoS

This solution runs as a part of the application plane above the SDN control plane. This solution communicates with the control plane using Rest API, so that rest_qos module which is part of Ryu (control plane) can handle the requests of this solution. rest_qos module acts as ovsdb-client and communicates with ovsdb-server provided by OVS in the data plane by ovsdb management protocol. 

This  solution applied using Fat Tree topology with scale 4. It creates 4 queues on switch ports for outbound traffic, so that one queue is dedicated only for micro flows, while elephant flows are forwarded out one of the remaining queues based on the port at which they arrived. It probes the queue length of micro flows based on dynamically changing intervals, and whenever micro queue length exceeds the predefined threshold, it detects elephant flows on that port. Then, it mitigates the transmission rate of the elephant queue on the upstream switch by a value proportional to the length of micro queue and elephant queue.  

Topology set up requires create queues with the following configurations:
create buffers with FIFO as queue discipline and 36 packets limit on buffer size:
tc qdisc add dev s$i-eth$j parent 1:$k pfifo limit 36
create queues with default transmission rates and Linux HTB (Hierarchy Token Buckets) to apply traffic shaping. For this sake, we use curl program to communicate with rest_qos module using Rest API.
curl -X POST -d '{"port_name": "s'$i'-eth'$j'", "type": "linux-htb", "max_rate": "100000000", "queues": [{"max_rate": "100000000"}, {"max_rate": "100000000"}, {"max_rate": "100000000"}, {"max_rate": "100000000"}]}' http://localhost:8080/qos/queue/0000000000000001
this curl command has the same impact as in http://www.openvswitch.org/support/dist-docs/ovs-vsctl.8.txt, example of Quality of Service (QoS) command.
In comparison to Sieve, this solution is not part of the control plane, but it is a part of the application plane. The following figure depicts the solution architecture:

