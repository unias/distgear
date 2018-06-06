#!/usr/bin/python3

import json
import os
import getopt
import time

import sys

# must first init loadenv
import tools, env
config = env.getenv("CONFIG")
tools.loadenv(config)

from log import initlogging
initlogging("docklet-web")
from log import logger

from flask import Flask, render_template, redirect, request, session, make_response
import requests
import auth, cookie_tool
import utils
from usermgr import UserManager
import proxytool

app = Flask(__name__)

@app.route("/", methods=['GET'])
def home():
    return render_template('home.html')

@app.route("/login/", methods=['GET'])
def login_get():
    if auth.is_authenticated():
        return redirect(request.args.get('next', None) or '/dashboard/')
    else:
        return render_template('login.html')

@app.route("/login/", methods=['POST'])
def login_post():
    if 'username' not in request.form or 'password' not in request.form:
        return redirect('/login/')
    user = request.form['username']
    password = request.form['password']
    if not utils.input_valid(user) or not utils.input_valid(password):
        return redirect('/login/')
    if app.userMgr.verify(user, password):
        status, userinfo = app.userMgr.get_user(user)
        resp = make_response(redirect(request.args.get('next', None) or '/dashboard/'))
        resp.set_cookie('docklet-jupyter-cookie', cookie_tool.generate_cookie(user, app.secret_key))
        session['username'] = user
        session['userid'] = userinfo['id']
        session['login-time'] = time.time()
        return resp
    else:
        return redirect('/login/')

@app.route("/logout/", methods=["GET"])
@auth.login_required
def logout():
    resp = make_response(redirect('/login/'))
    session.pop('username', None)
    session.pop('login-time', None)
    resp.set_cookie('docklet-jupyter-cookie', '', expires=0)
    return resp

@app.route("/register/", methods=['GET', 'POST'])
def register():
    if request.method != 'POST':
        return render_template('register.html')
    else:
        username = request.form.get('username')
        password = request.form.get('password')
        password2 = request.form.get('password2')
        if username == None or password == None or password != password2:
            return redirect('/register/')
        else:
            if not utils.input_valid(username) or not utils.input_valid(password):
                return redirect('/register/')
            if app.userMgr.user_exist(username):
                return redirect('/register/')
            status, info = app.userMgr.add_user(username, password)
            if status:
                return redirect('/login/')
            else:
                return redirect('/register/')

@app.route("/dashboard/", methods=['GET'])
@auth.login_required
def dashboard():
    userid = session['userid']
    username = session['username']
    status, clusters = app.userMgr.get_clusters(userid)
    if not status:
        clusters = []
    return render_template('dashboard.html', clusters=clusters, username=username)

# return a form to input the cluster information
@app.route("/workspace/create/", methods=['GET'])
@auth.login_required
def addCluster():
    username = session['username']
    return render_template('addCluster.html', username=username)

@app.route("/workspace/add/", methods=['POST'])
@auth.login_required
def createCluster():
    clustername = request.form['clusterName']
    userid = session['userid']
    username = session['username']
    if clustername=='' or app.userMgr.cluster_exist(clustername, userid):
        return redirect('/workspace/create/')
    """
    I have a not good idea.

    If we acquire some resource from mysql in master/distgear, that means 
    we need to implement a new mysql client in asyncio way. 

    so, if we acquire all resource in portal(here), the master/distgear just need 
    to schedule and dispatch commands. 

    time is limited. so we do it here. If we have time later, we will code a 
    asyncio mysql client and resource acquring in master/distgear.
    """
    """
    send event to DistGear Master to create cluster
    """
    # use try_add_cluster to occupy the clustername
    status, _ = app.userMgr.try_add_cluster(userid, clustername)
    if not status:
        return redirect('/workspace/create/')
    status, clusterid = app.userMgr.get_clusterid(clustername, userid)
    status, ips = app.userMgr.acquire_ips(userid)
    if not status:
        return redirect('/workspace/create/')
    # default size is 1
    ip = ips[0]
    ret = requests.post(app.master, data = json.dumps({
            'event':'CreateCluster',
            'parameters':{
                    'clustername':clustername,
                    'clusterid':clusterid,
                    'userid':userid,
                    'username':username,
                    'ip':ip+'/'+str(app.userMgr.cidr),
                    'authurl':app.authurl
                }
        }))
    try:
        result = json.loads(ret.text)
    except json.JSONDecodeError:
        print('result from master is not json')
        result = {'status':'fail', 'result':'result not json--%s'%result}
    if result['status'] == 'fail':
        app.userMgr.delete_cluster(clusterid)
        return redirect('/dashboard/')
    print('result from master: %s'%result)
    # containers in result is [ {'name':name, 'ip':ip, 'location':location} ]
    retcont = result['result']['containers']
    # containers : [ (name, clusterid, userid, status, ip, location ), ... ]
    containers = [ (x['name'], clusterid, userid, 'stopped', x['ip'], x['location']) for x in retcont]
    ret = app.userMgr.add_cluster(userid, clustername, clusterid, containers)
    print('add cluster ret: %s'%str(ret))
    return redirect('/dashboard/')

@app.route("/workspace/delete/<clustername>/", methods=['GET'])
@auth.login_required
def deleteCluster(clustername):
    userid = session['userid']
    status, clusterid = app.userMgr.get_clusterid(clustername, userid)
    if not status:
        return redirect('/dashboard/')
    status, clusterinfo = app.userMgr.get_clusterinfo(clusterid)
    if clusterinfo['status'] == 'running':
        return redirect('/dashboard/')
    """
    send event to DistGear Master to delete cluster
    """
    ret = requests.post(app.master, data = json.dumps({
            'event':'DeleteCluster',
            'parameters':{
                    'clustername':clustername,
                    'clusterid':clusterid,
                    'userid':clusterinfo['userid'],
                    'containers':clusterinfo['containers']
                }
        }))
    print('result from master: %s'%str(ret.text))
    try:
        result = json.loads(ret.text)
    except json.JSONDecodeError:
        print('result from master is not json')
        result = {'status':'fail', 'result':'result not json--%s'%result}
    if result['status'] == 'success':
        app.userMgr.delete_cluster(clusterid)
        containers = clusterinfo['containers']
        ips = [ x['ip'].split('/')[0] for x in containers ]
        print('want to release ips : %s'%str(ips))
        ret = app.userMgr.release_ips(userid, ips)
        print('release ips result : %s'%str(ret))
    else:
        print('ERROR : delete cluster failed')
    return redirect('/dashboard/')

@app.route("/workspace/start/<clustername>/", methods=['GET'])
@auth.login_required
def startCluster(clustername):
    userid = session['userid']
    username = session['username']
    status, clusterid = app.userMgr.get_clusterid(clustername, userid)
    if not status:
        return redirect('/dashboard/')
    status, clusterinfo = app.userMgr.get_clusterinfo(clusterid)
    if clusterinfo['status'] == 'running':
        return redirect('/dashboard/')
    """
    send event to DistGear Master to start cluster
    """
    ret = requests.post(app.master, data = json.dumps({
            'event':'StartCluster',
            'parameters':{
                    'clustername':clustername,
                    'clusterid':clusterid,
                    'userid':clusterinfo['userid'],
                    'containers':clusterinfo['containers']
                }
        }))
    print('result from master: %s'%str(ret.text))
    try:
        result = json.loads(ret.text)
    except json.JSONDecodeError:
        print('result from master is not json')
        result = {'status':'fail', 'result':'result not json--%s'%result}
    if result['status'] == 'success':
        app.userMgr.set_cluster_status(clusterid, 'running')
        target = 'http://'+clusterinfo['containers'][0]['ip'].split('/')[0]+':10000'
        proxytool.set_route('go/%s/%s'%(username, clustername), target)
    else:
        print('ERROR : start cluster failed')
    return redirect('/dashboard/')

@app.route("/workspace/stop/<clustername>/", methods=['GET'])
@auth.login_required
def stopCluster(clustername):
    userid = session['userid']
    username = session['username']
    status, clusterid = app.userMgr.get_clusterid(clustername, userid)
    if not status:
        return redirect('/dashboard/')
    status, clusterinfo = app.userMgr.get_clusterinfo(clusterid)
    if clusterinfo['status'] == 'stopped':
        return redirect('/dashboard/')
    """
    send event to DistGear Master to start cluster
    """
    ret = requests.post(app.master, data = json.dumps({
            'event':'StopCluster',
            'parameters':{
                    'clustername':clustername,
                    'clusterid':clusterid,
                    'userid':clusterinfo['userid'],
                    'containers':clusterinfo['containers']
                }
        }))
    print('result from master: %s'%str(ret.text))
    try:
        result = json.loads(ret.text)
    except json.JSONDecodeError:
        print('result from master is not json')
        result = {'status':'fail', 'result':'result not json--%s'%result}
    if result['status'] == 'success':
        app.userMgr.set_cluster_status(clusterid, 'stopped')
        proxytool.delete_route('go/%s/%s'%(username, clustername))
    else:
        print('ERROR : stop cluster failed')
    return redirect('/dashboard/')

# URLs for jupyter 
@app.route('/index/', methods=['GET'])
def jupyter_control():
    return redirect('/dashboard/')

@app.route('/jupyter/', methods=['GET'])
def jupyter_prefix():
    path = request.args.get('next')
    if path == None:
        return redirect('/login/')
    return redirect('/login/'+'?next='+path)

@app.route('/jupyter/home/', methods=['GET'])
def jupyter_home():
    return redirect('/dashboard/')

@app.route('/jupyter/login/', methods=['GET', 'POST'])
def jupyter_login():
    return redirect('/login/')

@app.route('/jupyter/logout/', methods=['GET'])
def jupyter_logout():
    return redirect('/logout/')

@app.route('/jupyter/authorizations/cookie/<cookie_name>/<cookie_content>/', methods=['GET'])
def jupyter_auth(cookie_name, cookie_content):
    username = cookie_tool.parse_cookie(cookie_content, app.secret_key)
    if username == None:
        resp = make_response('cookie auth failed')
        resp.status_code = 404
        return resp
    return json.dumps({'name': username})



if __name__ == '__main__':
    '''
    to generate a secret_key

    from base64 import b64encode
    from os import urandom

    secret_key = urandom(24)
    secret_key = b64encode(secret_key).decode('utf-8')

    '''
    logger.info('Start Flask...:')
    try:
        secret_key_file = open(env.getenv('FS_PREFIX') + '/local/web_secret_key.txt')
        app.secret_key = secret_key_file.read()
        secret_key_file.close()
    except:
        from base64 import b64encode
        from os import urandom
        secret_key = urandom(24)
        secret_key = b64encode(secret_key).decode('utf-8')
        app.secret_key = secret_key
        secret_key_file = open(env.getenv('FS_PREFIX') + '/local/web_secret_key.txt', 'w')
        secret_key_file.write(secret_key)
        secret_key_file.close()

    os.environ['APP_KEY'] = app.secret_key
    runcmd = sys.argv[0]
    app.runpath = runcmd.rsplit('/', 1)[0]

    webip = "0.0.0.0"
    webport = env.getenv("WEB_PORT")
    mysql_host = env.getenv("MYSQL").strip('\'"')
    print(mysql_host)

    app.master = 'http://%s:%d' % (env.getenv('MASTER_IP'), env.getenv('MASTER_PORT'))
    app.userMgr = UserManager(mysql_host=mysql_host)
    ipaddr = tools.getip(env.getenv('NETWORK_DEVICE'))
    if ipaddr == False:
        print ("get ip failed")
        sys.exit(2)
    app.authurl = 'http://'+ipaddr+':8888/jupyter'

    try:
        opts, args = getopt.getopt(sys.argv[1:], "i:p:", ["ip=", "port="])
    except getopt.GetoptError:
        print ("%s -i ip -p port" % sys.argv[0])
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-i", "--ip"):
            webip = arg
        elif opt in ("-p", "--port"):
            webport = int(arg)

    app.run(host = webip, port = webport, threaded=True,)

