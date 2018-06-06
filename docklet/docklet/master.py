#!/usr/bin/python3
# -*- coding: utf-8 -*-

import tools, env
config = env.getenv("CONFIG")
tools.loadenv(config)
fs_prefix = env.getenv('FS_PREFIX')

import random

import distgear

master = distgear.PrimaryMaster('docklet-master', logpath=fs_prefix+'/local/log', http_addr='0.0.0.0:9000', pub_addr='0.0.0.0:9001', pull_addr='0.0.0.0:9002')

@master.handleEvent('CreateCluster')
async def create_cluster(event, master):
    print('< Create Cluster >')
    print('para: %s' % str(event.paras))
    clustername = event.paras['clustername']
    clusterid = event.paras['clusterid']
    userid = event.paras['userid']
    username = event.paras['username']
    authurl = event.paras['authurl']
    ip = event.paras['ip']
    container = str(userid)+'-'+str(clusterid)+'-'+'0'
    workers = list(master.get_nodeinfo().keys())
    if len(workers) == 0:
        return {'status':'fail', 'result':'no workers'}
    worker = workers[random.randint(0, len(workers)-1)]
    paras = { 'name':container,
              'ip':ip,
              'authurl':authurl,
              'username':username,
              'clustername':clustername,
              'gateway':'172.16.0.1'
              }
    result = await event.run_command((worker, 'CreateContainer', paras), timeout=10)
    if result['status'] == 'fail':
        return {'status':'fail', 'result':'create container failed'}
    content = { 'cluster':clustername,
                'containers':[ {'name':container, 'ip':ip, 'location':worker} ],
                'status':'stopped'
            }
    return {'status':'success', 'result':content}

@master.handleEvent('DeleteCluster')
async def delete_cluster(event, master):
    print('< Delete Cluster >')
    print('para: %s' % str(event.paras))
    containers = event.paras['containers']
    cmds = {}
    for cont in containers:
        cmds[cont['name']] = (cont['location'], 'DeleteContainer', {'name':cont['name']},[])
    ret = await event.run(cmds)
    print('return is :%s'%str(ret))
    fails = list(filter(lambda cmd: ret[cmd]['status']!='success', ret))
    if len(fails)==0:
        return {'status':'success', 'result':'delete container success'}
    else:
        return {'status':'fail', 'result':'delete container fail'}

@master.handleEvent('StartCluster')
async def start_cluster(event, master):
    print('< Start Cluster >')
    print('para: %s' % str(event.paras))
    containers = event.paras['containers']
    cmds = {}
    for cont in containers:
        cmds[cont['name']] = (cont['location'], 'StartContainer', {'name':cont['name']},[])
    ret = await event.run(cmds)
    print('return is :%s'%str(ret))
    fails = list(filter(lambda cmd: ret[cmd]['status']!='success', ret))
    if len(fails)==0:
        return {'status':'success', 'result':'start container success'}
    else:
        return {'status':'fail', 'result':'start container fail'}

@master.handleEvent('StopCluster')
async def stop_cluster(event, master):
    print('< Stop Cluster >')
    print('para: %s' % str(event.paras))
    containers = event.paras['containers']
    cmds = {}
    for cont in containers:
        cmds[cont['name']] = (cont['location'], 'StopContainer', {'name':cont['name']},[])
    ret = await event.run(cmds)
    print('return is :%s'%str(ret))
    fails = list(filter(lambda cmd: ret[cmd]['status']!='success', ret))
    if len(fails)==0:
        return {'status':'success', 'result':'stop container success'}
    else:
        return {'status':'fail', 'result':'stop container fail'}


master.start()

