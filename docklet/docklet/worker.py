#!/usr/bin/python3
# -*- coding: utf-8 -*-

import tools, env
config = env.getenv("CONFIG")
tools.loadenv(config)

import getopt, sys
import os
import asyncio
import shutil

import distgear

async def runcmd(*args, shell=False):
    if shell:
        process = await asyncio.create_subprocess_shell(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    else:
        process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout = await process.stdout.read()
    stderr = await process.stderr.read()
    await process.wait()
    retcode = process.returncode
    return retcode, bytes.decode(stdout), bytes.decode(stderr)


name = None
master = "127.0.0.1"
pubport, pullport = 9001, 9002
try:
    opts, args = getopt.getopt(sys.argv[1:], "n:m:b:l", ["name=", "master=", "pubport=", "pullport="])
except getopt.GetoptError:
    print("%s -n name -m master -b pubport -l pullport" % sys.argv[0])
    sys.exit(1)
for opt, arg in opts:
    if opt in ("-n", "--name"):
        name = arg
    elif opt in ("-m", "--master"):
        master = arg
    elif opt in ("-b", "--pubport"):
        pubport = int(arg)
    elif opt in ("-l", "--pullport"):
        pullport = int(arg)

# name should be got from args, here for test
name='worker-1'

if name is None:
    print('name is necessary')
    sys.exit(1)

fs_prefix = env.getenv("FS_PREFIX")
worker = distgear.Worker(name, logpath=fs_prefix+'/local/log', master_pub_addr=master+':'+str(pubport), master_pull_addr=master+':'+str(pullport))
baseconffile = open(env.getenv('DOCKLET_CONF')+'/container.conf', 'r')
baseconf = baseconffile.read()
baseconffile.close()

@worker.doAction('CreateContainer')
async def create_container(paras):
    print('create container with paras: %s'%paras)
    name = paras['name']
    username = paras['username']
    clustername = paras['clustername']
    authurl = paras['authurl']
    gateway = paras['gateway']
    base = fs_prefix + "/local/basefs"
    ip = paras['ip']
    layer = fs_prefix + "/local/volume/" + name
    os.mkdir(layer)
    os.mkdir("/var/lib/lxc/%s"%name)
    rootfs = "/var/lib/lxc/%s/rootfs"%name
    os.mkdir(rootfs)
    confpath = "/var/lib/lxc/%s/config"%name
    retcode, stdout, stderr = await runcmd('mount', '-t', 'aufs', '-o', 'br=%s=rw:%s=ro+wh'%(layer, base), '-o', 'udba=reval', 'none', rootfs)
    #retcode, stdout, stderr = await runcmd('mount -t aufs -o br=%s=rw:%s=ro+wh -o udba=reval none %s'%(layer, base, rootfs), shell=True)
    if retcode!=0:
        print('umount failed')
        return {'status':'fail', 'result':'delete container fail for umount fail'}
    def gen_config(content):
        content = content.replace("%ROOTFS%",rootfs)
        content = content.replace("%HOSTNAME%",name)
        content = content.replace("%IP%",ip)
        content = content.replace("%GATEWAY%",gateway)
        #content = content.replace("%CONTAINER_MEMORY%",str(memory))
        #content = content.replace("%CONTAINER_CPU%",str(cpu))
        #content = content.replace("%FS_PREFIX%",self.fspath)
        #content = content.replace("%USERNAME%",username)
        #content = content.replace("%CLUSTERID%",str(clusterid))
        content = content.replace("%LXCSCRIPT%",env.getenv("LXC_SCRIPT"))
        content = content.replace("%LXCNAME%",name)
        #content = content.replace("%VLANID%",str(vlanid))
        #content = content.replace("%CLUSTERNAME%", clustername)
        content = content.replace("%VETHPAIR%", name)
        return content
    newconf = gen_config(baseconf)
    conffile = open(confpath, 'w')
    conffile.write(newconf)
    conffile.close()
    cookiename = 'docklet-jupyter-cookie'
    jconfpath = rootfs+'/home/jupyter/jupyter.config'
    jconffile = open(jconfpath, 'w')
    jconfig="""USER=%s
PORT=%d
COOKIE_NAME=%s
BASE_URL=%s
HUB_PREFIX=%s
HUB_API_URL=%s
IP=%s
""" % (username, 10000, cookiename, '/go/'+username+'/'+clustername, '/jupyter',
        authurl, ip.split('/')[0])
    jconffile.write(jconfig)
    jconffile.close()
    return {'status':'success', 'result':'create container success'}

@worker.doAction('DeleteContainer')
async def delete_container(paras):
    print('delete container with paras: %s'%paras)
    name = paras['name']
    retcode, stdout, stderr = await runcmd('umount', '/var/lib/lxc/%s/rootfs'%name)
    if retcode!=0:
        print('umount failed')
        return {'status':'fail', 'result':'delete container fail for umount fail'}
    shutil.rmtree('/var/lib/lxc/%s'%name)
    shutil.rmtree(fs_prefix+'/local/volume/'+name)
    return {'status':'success', 'result':'delete container success'}

@worker.doAction('StartContainer')
async def start_container(paras):
    print('start container with paras: %s'%paras)
    name = paras['name']
    retcode, stdout, stderr = await runcmd('lxc-start -n %s'%name, shell=True)
    if retcode!=0:
        print('start container failed')
        return {'status':'fail', 'result':'start container fail'}
    retcode, stdout, stderr = await runcmd('lxc-attach -n %s -- su -c /home/jupyter/start_jupyter.sh'%(name), shell=True)
    if retcode!=0:
        print('start jupyter failed')
        return {'status':'fail', 'result':'start jupyter fail'}
    return {'status':'success', 'result':'start container success'}
 
@worker.doAction('StopContainer')
async def stop_container(paras):
    print('stop container with paras: %s'%paras)
    name = paras['name']
    retcode, stdout, stderr = await runcmd('lxc-stop -k -n %s'%name, shell=True)
    if retcode!=0:
        print('stop failed')
        return {'status':'fail', 'result':'stop container fail'}
    return {'status':'success', 'result':'stop container success'}
 

worker.start()

 


