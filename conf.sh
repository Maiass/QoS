#!/bin/bash
# Copyright (C) 2021 Maiass Zaher at Budapest University 
# of Technology and Economics, Budapest, Hungary.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.


#This Bash configures the data plane devices. It deletes all queue disciplines (packet schedulers), queues and Qos rules already existed
#on OVS switches in the data plane. It starts OVSDB server, connects OVS switches with OVSDB server, create HTB queues on OVS switches and 
#sets queue length limit and FIFO schedulers (qdisc) for the new created queues using Netem provided by Linux kernel. 
#The following steps should be executed in order.

#delete all qdisc of all ports
for i in {1..20}
do
  for j in {1..4}
  do
    tc qdisc del dev s$i-eth$j root
  done
done

#delete all Qos and Queues
ovs-vsctl --all destroy Qos
ovs-vsctl --all destroy Queue

#Start OVSDB server
ovs-vsctl set-manager ptcp:6632

#connect OVSDB server with switches through Rest API provided by QoS module of SDN controller 
for i in {1..20}
do
  a="$(printf '%016x' $i)"
  curl -X PUT -d '"tcp:127.0.0.1:6632"' http://localhost:8080/v1.0/conf/switches/$a/ovsdb_addr
done

#create queues on Core switches
for i in {1..4}
do
  for j in {1..4}
  do
    curl -X POST -d '{"port_name": "s'$i'-eth'$j'", "type": "linux-htb", "max_rate": "100000000", "queues": [{"max_rate": "100000000"}, {"max_rate": "100000000"}, {"max_rate": "100000000"}, {"max_rate": "100000000"}]}' http://localhost:8080/qos/queue/000000000000000$i
  done
done

#create queues on Aggregate switches (sw5, sw6, sw7, sw8, sw9, sw10, sw11, sw12) ports connected to Core and ToR switches
for i in {5..12}
do
  for j in {1..4}
  do
  	a="$(printf '%016x' $i)"
  	if [[ $j -gt 2 ]]
	then
    	curl -X POST -d '{"port_name": "s'$i'-eth'$j'", "type": "linux-htb", "max_rate": "100000000", "queues": [{"max_rate": "100000000"}, {"max_rate": "100000000"}, {"max_rate": "100000000"}, {"max_rate": "100000000"}]}' http://localhost:8080/qos/queue/$a
	else
		curl -X POST -d '{"port_name": "s'$i'-eth'$j'", "type": "linux-htb", "max_rate": "10000000", "queues": [{"max_rate": "10000000"}, {"max_rate": "10000000"}, {"max_rate": "10000000"}, {"max_rate": "10000000"}]}' http://localhost:8080/qos/queue/$a
	fi
  done
done

#create queues on ToR switch ports connected to Aggregate switches and End-hosts

for i in {13..20}
do
  for j in {1..4}
  do
  	a="$(printf '%016x' $i)"
  	if [[ $j -gt 2 ]]
	then
    	curl -X POST -d '{"port_name": "s'$i'-eth'$j'", "type": "linux-htb", "max_rate": "10000000", "queues": [{"max_rate": "10000000"}, {"max_rate": "10000000"}, {"max_rate": "10000000"}, {"max_rate": "10000000"}]}' http://localhost:8080/qos/queue/$a
	else
		curl -X POST -d '{"port_name": "s'$i'-eth'$j'", "type": "linux-htb", "max_rate": "5000000", "queues": [{"max_rate": "5000000"}, {"max_rate": "5000000"}, {"max_rate": "5000000"}, {"max_rate": "5000000"}]}' http://localhost:8080/qos/queue/$a
	fi
  done
done

# set queue length to 36 packets of all queues on all switch ports and set FIFO as the queue discipline by Netem
for i in {1..20}
do
  for j in {1..4}
  do
    for k in {1..4}
	do
      tc qdisc add dev s$i-eth$j parent 1:$k pfifo limit 36
    done
  done
done




