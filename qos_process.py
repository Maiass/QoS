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
"""
	It checks the queue length by using TC utility. When micro flow queue length
	passes the predefined threshold, this module connects with sFlow
	using Rest API to bring elephant flow information forwarding out that port.
	Then it creates new QoS rules in OVS switches using rest_qos module provided
	by the controller using Rest API to mitigate the transmission rate of elephant
	flows to save flow completion time (FCT) of mice flows.
"""

from __future__ import division
from time import sleep, time
from subprocess import *
import re
import requests
import json
from mininet.util import quietRun
import copy

default_dir = '.'

class Qos:
	def __init__(self, ql_max, ql_min, rules_dict):
		self.ql_max = ql_max
		self.ql_min = ql_min
		self.rules_dict = {}
		
	def monitor_qlen(self):
		#monitoring the queue length of switch port by regular expression and a tc command
		pat_queued =re.compile(r'backlog\s[^\s]+\s([\d]+)p')
		#command dev name should same as file name
		cmd = "tc -s class show dev s5-eth2"
		eventurl, eventID = self.create_sflow_entry()
		#monitoriing the queue length all the time
		while 1: 
			p = Popen(cmd, shell=True, stdout=PIPE)
			output = p.stdout.read()
			matches = pat_queued.findall(output)
			if matches and len(matches) > 0:
				#check if the queue length passed the threshold
				if int(matches[1]) >= self.ql_min:
					#alpha is coefficient of queue length of this port
					alpha = (int(matches[1])-self.ql_min)/(self.ql_max-self.ql_min)
					r = requests.get(eventurl + "&eventID=" + str(eventID))
					#if there aren't elephant flows, so do no thing
					if r.status_code == 200:
						events = r.json()
						if len(events) == 0: print "No elephant flows:", r.text
						else:
							eventID = events[0]["eventID"]
							events.reverse()
							for e in events:
								#split the flow keys into array list[0]=ipsource,list[1]=ipdestination,list[2]=tcpsourceport,list[3]=tcpdestinationport,list[4]=inputifindex,list[5]=outputifindex
								list = e['flowKey'].split(',')
								self.redirect_elephant(list[0], list[1], list[2], list[3], list[4], alpha, self.ql_max)
				else:
					#delete old Qos rules in case the micro flow queue length is below the threshold
					self.delete_old_qos_rules()
			#monitoring interval is proportional to queue length of this port.
			#if (ql > 0) : interval_sec = ((Th/int(matches[0]))*RTT)/1000 else: interval_sec = (Th * RTT)/1000
			if int(matches[1]) > 0 :
			interval_sec = ((33/(int(matches[1])))*11)/1000
			else:
			interval_sec = 33*11/1000
			sleep(interval_sec)

	def create_sflow_entry(self):
		#check the elephant flows arrive to this port from its internal source ports by defining a new flow entry in SFlow
		rt = 'http://127.0.0.1:8008'
		#use the port index assigned by SFlow
		flow = {'keys':'ipsource,ipdestination,tcpsourceport,tcpdestinationport,inputifindex,outputifindex','value':'bytes', 'filter':'outputifindex=2034&inputifindex=2305,2302,2313'}
		#create SFlow flow entry whose name matches the name of the port
		requests.put(rt+'/flow/port_5-2/json',data=json.dumps(flow))
		#define a threshold for the previous SFlow entry should have name matches the port name, so that each flow whose size more than 10KB will be recorded in SFlow database
		threshold = {'metric':'port_5-2','value':10480,'byFlow':True,'timeout':0.1}
		requests.put(rt+'/threshold/elephant_5-2/json',data=json.dumps(threshold))
		eventurl = rt+'/events/json?thresholdID=elephant_5-2&maxEvents=1'
		eventID = -1
		return eventurl, eventID

	def redirect_elephant(self, ip_src, ip_dst, port_src, port_dst, port_no, alpha, ql_max):
		#internal source port : s5-eth4 connected to s13-eth4
		if port_no == '2313':
			#measure the mitigation value of elephant flows transmission rate
			rate = self.measure_rate(port_no, 's13-eth4', alpha, ql_max)
			#create queues with the new transmission rate
			data1 = { 'port_name': 's13-eth4', 'type': 'linux-htb', 'max_rate':'5000000', 'queues': [{'max_rate': '5000000'}, {'max_rate': '5000000'}, {'max_rate': str(rate)}, {'max_rate': '5000000'}]}
			#matched elephant flows arrive from external source port to this port, will be enqueue to the queue dedicated for this port to mitigate its transmission rate
			data2 = {'hard_timeout':'5', 'match': {'nw_src': ip_src, 'nw_dst': ip_dst, 'nw_proto': 'TCP', 'tp_src': port_src, 'tp_dst': port_dst}, 'actions':{'queue': '3'}}
		#internal source port : s5-eth3 connected to s13-eth3
		elif port_no == '2305':
			rate = self.measure_rate(port_no, 's13-eth3', alpha, ql_max)
			data1 = { 'port_name': 's13-eth4', 'type': 'linux-htb', 'max_rate':'5000000', 'queues': [{'max_rate': '5000000'}, {'max_rate': str(rate)}, {'max_rate': '5000000'}, {'max_rate': '5000000'}]}
			data2 = {'hard_timeout':'5', 'match': {'nw_src': ip_src, 'nw_dst': ip_dst, 'nw_proto': 'TCP', 'tp_src': port_src, 'tp_dst': port_dst}, 'actions':{'queue': '2'}}
		#internal source port : s5-eth1 connected to s13-eth1
		else:
			rate = self.measure_rate(port_no, 's13-eth1', alpha, ql_max)
			data1 = { 'port_name': 's13-eth4', 'type': 'linux-htb', 'max_rate':'5000000', 'queues': [{'max_rate': str(rate)}, {'max_rate': '5000000'}, {'max_rate': '5000000'}, {'max_rate': '5000000'}]}
			data2 = {'hard_timeout':'5', 'match': {'nw_src': ip_src, 'nw_dst': ip_dst, 'nw_proto': 'TCP', 'tp_src': port_src, 'tp_dst': port_dst}, 'actions':{'queue': '1'}}
		r1 = requests.post('http://localhost:8080/qos/queue/000000000000000d', data=json.dumps(data1))
		r2 = requests.post('http://localhost:8080/qos/rules/000000000000000d', data=json.dumps(data2))
		#save QoS rules IDs in a dictionary
		self.save_rules(r2, ip_src, ip_dst, port_src, port_dst)

	def measure_rate(self, port_no, int_name, alpha, ql_max):
		pat_queued1 =re.compile(r'backlog\s[^\s]+\s([\d]+)p')
		cmd1 = "tc -s qdisc show dev"+int_name
		p1 = Popen(cmd1, shell=True, stdout=PIPE)
		output1 = p1.stdout.read()
		matches1 = pat_queued1.findall(output1)
		if matches1 and len(matches1) > 0:
		  #beta is coefficient of queue length of the external source port
		  beta = (ql_max-int(matches1[1]))/(ql_max)
		  #new rate is function of the BW of the link between this port and its external source port, s.t. maximum reduction will be 50%
		  return int(5000000*(1-((alpha*beta)/2)))

	def save_rules(self, r2, ip_src, ip_dst, port_src, port_dst):
		r_json = r2.json()
		rule_msg = r_json[0]['command_result'][0]['details']
		qos_id_list = rule_msg.split('=')
		qos_id = qos_id_list[1]
		#create a dictionary for active elephant flows between this port and its upstream switch
		self.rules_dict[ip_src+','+ip_dst+','+port_src+','+port_dst] = qos_id

	def delete_old_qos_rules(self):
		for ruleid in self.rules_dict.keys():
			rule_for_delete = {'qos_id': self.rules_dict[ruleid]}
			rule_for_delete_req = requests.delete('http://localhost:8080/qos/rules/000000000000000d', data=json.dumps(rule_for_delete))
			print "deleted queue rules after queue length went below threshold:", rule_for_delete_req, self.rules_dict[ruleid]
			del self.rules_dict[ruleid]

if __name__ == '__main__':
	#maximum and minimum of queue length ql_max=BDP (BandwidthDelayProduct=BW*RTT) =queue capacity, ql_min = Th = ql_max-(k-1)pkt
	qos1 = Qos(36,32)
	qos1.monitor_qlen()
