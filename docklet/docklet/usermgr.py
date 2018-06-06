# -*- coding: utf-8 -*-

import hashlib

import pymysql

from utils import input_valid
from tools import ip_to_int, int_to_ip

class UserManager(object):
    def __init__(self, mysql_host='localhost', mysql_port=3306, database='docklet', user='docklet', passwd='unias'):
        self.mysql = (mysql_host, mysql_port)
        self.db = database
        self.user = user
        self.passwd = passwd
        self.conn = pymysql.connect(host=mysql_host, port=mysql_port, db=database,
                user=user, passwd=passwd, cursorclass=pymysql.cursors.DictCursor)
        self.userTable = 'users'
        self.clusterTable = 'clusters'
        self.containerTable = 'containers'
        self.addressTable = 'addresses'
        self.cidr = 24
        self.step = 4

    def try_table(self):
        ret = None
        with self.conn.cursor() as cursor:
            try:
                cursor.execute('describe %s' % self.userTable)
                cursor.execute('describe %s' % self.clusterTable)
                cursor.execute('describe %s' % self.containerTable)
                cursor.execute('describe %s' % self.addressTable)
                ret = (True, 'try user/cluster/container/address tables success')
            except pymysql.ProgrammingError as e:
                ret = (False, str(e))
        return ret

    def create_table(self):
        usersql = """
        create table %s( id int not null auto_increment,
                         name varchar(20) not null,
                         password char(40) not null,
                         containers int default 0, 
                         primary key (id), unique index nameindex (name) 
        )"""%self.userTable
        clustersql = """
        create table %s( id int not null auto_increment,
                         name varchar(40) not null,
                         userid int not null,
                         size int not null default 0,
                         status char(10) not null,
                         primary key (id), 
                         index nameindex(name), index userindex(userid),
                         unique index nameuser(name, userid)
        )"""%self.clusterTable
        containersql = """
        create table %s( id int not null auto_increment,
                         name varchar(50) not null,
                         clusterid int not null,
                         userid int not null,
                         status char(10) not null,
                         ip char(20) not null,
                         location char(30) not null,
                         primary key(id),
                         index nameindex(name), index clusterindex(clusterid),
                         index userindex(userid),
                         unique index usercon(name, clusterid, userid)
        )"""%self.containerTable
        # userid : +X is some user, 0 is system, -1 is unused
        addresssql = """
        create table %s( domain char(20) not null,
                         userid int not null default -1,
                         available varchar(100),
                         primary key(domain),
                         index userindex(userid)
        )"""%self.addressTable
        ret = (False, 'sql execute error')
        with self.conn.cursor() as cursor:
            cursor.execute(usersql)
            cursor.execute(clustersql)
            cursor.execute(containersql)
            cursor.execute(addresssql)
            network, cidr, step, sysnum = '172.16.0.0', self.cidr, self.step, 1
            available = ','.join([ str(i) for i in range(1, (1<<step)-1) ])
            sys = [ (int_to_ip(ip_to_int(network)+index*(1<<step)), 0, available) for index in range(sysnum) ]
            unused = [ (int_to_ip(ip_to_int(network)+index*(1<<step)), -1, available) for index in range(sysnum, 1<<(32-cidr-step)) ]
            cursor.executemany("insert into "+self.addressTable+" (domain, userid, available) values (%s, %s, %s)", sys+unused)
            try:
                self.conn.commit()
                ret = (True, 'create tables success')
            except:
                self.conn.rollback()
                ret = (False, 'create tables fail')
        return ret

    def close(self):
        try:
            self.conn.commit()
        except:
            self.conn.rollback()
        self.conn.close()

    def get_user(self, username):
        if not input_valid(username):
            return (False, 'username is invalid')
        ret = None
        with self.conn.cursor() as cursor:
            records = cursor.execute("select * from %s where name='%s'"%(self.userTable, username))
            if records == 0:
                ret = (False, 'username:%s not exists'%username)
            else:
                ret = (True, cursor.fetchone())
        return ret
            
    def user_exist(self, username):
        ret = self.get_user(username)
        return ret[0]

    def add_user(self, username, passwd, containers=0):
        if self.user_exist(username):
            return (False, 'username already exists')
        hashpass = hashlib.md5(str.encode(passwd)).hexdigest()
        ret = None
        with self.conn.cursor() as cursor:
            cursor.execute("insert into %s (name, password, containers) values ('%s','%s',%d)"%(self.userTable, username, hashpass, containers))
            records = cursor.execute("select * from %s where userid=-1"%self.addressTable)
            if records == 0:
                ret = (False, 'no network addresses for new user:%s'%username)
                # I think rollback here is necessary
                self.conn.rollback()
            else:
                network = cursor.fetchone() 
                cursor.fetchall()
                cursor.execute("select * from %s where name='%s'"%(self.userTable, username))
                userinfo = cursor.fetchone()
                userid = userinfo['id']
                cursor.execute("update %s set userid=%d where domain='%s'"%(self.addressTable, userid, network['domain']))
                try:
                    self.conn.commit()
                    ret = (True, 'add user:%s success'%username)
                except pymysql.Error as e:
                    self.conn.rollback()
                    ret = (False, 'add user:%s fail, %s'%str(e))
        return ret

    def acquire_ips(self, userid, num = 1):
        if num<=0:
            return (True, [])
        ret = (False, 'sql execute error')
        with self.conn.cursor() as cursor:
            records = cursor.execute("select * from %s where userid=%d"%(self.addressTable, userid))
            if records == 0:
                ret = (False, 'error: user(id:%d) has no network line in address table'%userid)
            else:
                # right now, each user has only one network line
                network = cursor.fetchone()
                available = network['available']
                domain = network['domain']
                addr = available.split(',', maxsplit=num) if available!='' else []
                if len(addr) < num:
                    ret = (False, "not enough addresses for this acquire")
                else:
                    left = '' if len(addr)==num else addr[num]
                    cursor.execute("update %s set available='%s' where domain='%s'"%(self.addressTable, left, domain))
                    ret = (True, [ int_to_ip(ip_to_int(domain)+int(one)) for one in addr[:num] ] )
                    try:
                        self.conn.commit()
                    except pymysql.Error as e:
                        self.conn.rollback()
                        ret = (False, 'acquire address fail, %s'%str(e))
        return ret

    def release_ips(self, userid, ips):
        if ips==[]:
            return (True, ips)
        ret = (False, 'sql execute error')
        with self.conn.cursor() as cursor:
            records = cursor.execute("select * from %s where userid=%d"%(self.addressTable, userid))
            if records == 0:
                ret = (False, 'error: user(id:%d) has no network line in address table'%userid)
            else:
                # right now, each user has only one network line
                network = cursor.fetchone()
                available = network['available']
                domain = network['domain']
                append = ','.join([str(ip_to_int(ip)-ip_to_int(domain)) for ip in ips])
                update = append if available=='' else available+','+append
                cursor.execute("update %s set available='%s' where domain='%s'"%(self.addressTable, update, domain))
                try:
                    self.conn.commit()
                    ret = (True, ips)
                except pymysql.Error as e:
                    self.conn.rollback()
                    ret = (False, 'release address fail, %s'%str(e))
        return ret
 
    def verify(self, name, passwd):
        status, user = self.get_user(name)
        if not status:
            return False
        hashpass = user['password']
        if hashpass == hashlib.md5(str.encode(passwd)).hexdigest():
            return True
        else:
            return False

    def try_add_cluster(self, userid, clustername, status='stopped'):
        """just insert the clustername to occupy the name of cluster
        in case after we create the cluster, some one insert the same clustername
        """
        with self.conn.cursor() as cursor:
            cursor.execute("insert into %s (name, userid, size, status) values ('%s', %d, %d, '%s')"%(self.clusterTable, clustername, userid, 0, status))
            try:
                self.conn.commit()
                ret = (True, 'try add cluster:%s success'%clustername)
            except:
                self.conn.rollback()
                ret = (False, 'try add cluster:%s fail'%clustername)
        return ret

    def add_cluster(self, userid, clustername, clusterid, containers, status='stopped'):
        """add cluster and containers into tables
        containers: [ (name, clusterid, userid, status, ip, location), ... ]
        """
        ret = (False, 'error occurs when execute sql')
        with self.conn.cursor() as cursor:
            size = len(containers)
            # here, we use string format to join sql command
            # execute('...'%(...)) 
            # another format is pymysql format, see below
            #cursor.execute("insert into %s (name, userid, size, status) values ('%s', %d, %d, '%s')"%(self.clusterTable, clustername, userid, size, status))
            cursor.execute("update %s set size=%d where id=%d"%(self.clusterTable, size, clusterid))
            cursor.execute("update %s set containers=containers+%d where id=%d"%(self.userTable, size, userid))
            # here, we use pymysql format to join sql command
            # execute('...', (...))
            # execute/executemany will convert args to the sql.
            # args in sql should all be %s
            # integer in args list will be convert into str(int)
            # str in args list will be convert into 'str'
            # another format is string format, see above
            cursor.executemany("insert into "+self.containerTable+" (name, clusterid, userid, status, ip, location) values (%s, %s, %s, %s, %s, %s)", containers)
            try:
                self.conn.commit()
                ret = (True, 'add cluster:%s success'%clustername)
            except:
                self.conn.rollback()
                ret = (False, 'add cluster:%s fail'%clustername)
        return ret

    def delete_cluster(self, clusterid):
        """add cluster into tables
        """
        ret = (False, 'error occurs when execute sql')
        status, clusterinfo = self.get_clusterinfo(clusterid)
        if not status:
            return (False, 'no cluster with id:%d'%clusterid)
        with self.conn.cursor() as cursor:
            clustername = clusterinfo['name']
            size = clusterinfo['size']
            userid = clusterinfo['userid']
            cursor.execute("update %s set containers=containers-%d where id=%d"%(self.userTable, size, userid))
            cursor.execute("delete from %s where id=%d"%(self.clusterTable, clusterid))
            cursor.execute("delete from %s where clusterid=%d"%(self.containerTable, clusterid))
            try:
                self.conn.commit()
                ret = (True, 'delete cluster:%s success'%clustername)
            except:
                self.conn.rollback()
                ret = (False, 'delete cluster:%s fail'%clustername)
        return ret

    def set_cluster_status(self, clusterid, clusterstatus):
        ret = (False, 'error occurs when execute sql')
        status, clusterinfo = self.get_clusterinfo(clusterid)
        if not status:
            return (False, 'no cluster with id:%d'%clusterid)
        with self.conn.cursor() as cursor:
            cursor.execute("update %s set status='%s' where id=%d"%(self.clusterTable, clusterstatus, clusterid))
            cursor.execute("update %s set status='%s' where clusterid=%d"%(self.containerTable, clusterstatus, clusterid))
            try:
                self.conn.commit()
                ret = (True, 'update cluster status success')
            except:
                self.conn.rollback()
                ret = (False, 'update cluster status fail')
        return ret

    def get_clusters(self, userid):
        ret = (False, 'error occurs when execute sql')
        with self.conn.cursor() as cursor:
            cursor.execute("select * from %s where userid=%d"%(self.clusterTable, userid))
            ret = (True, cursor.fetchall())
        return ret

    def cluster_exist(self, clustername, userid):
        status, clusters = self.get_clusters(userid)
        if not status:
            return False
        for cluster in clusters:
            if clustername == cluster['name']:
                return True
        return False

    def get_clusterid(self, clustername, userid):
        ret = (False, 'error occurs when execute sql')
        with self.conn.cursor() as cursor:
            records = cursor.execute("select * from %s where userid=%d and name='%s'"%(self.clusterTable, userid, clustername))
            if records == 0:
                ret = (False, 'no cluster:%s'%clustername)
            else:
                ret = (True, cursor.fetchone()['id'])
        return ret

    def get_clusterinfo(self, clusterid):
        ret = (False, 'error occurs when execute sql')
        with self.conn.cursor() as cursor:
            cursor.execute("select * from %s where id=%d" %(self.clusterTable, clusterid))
            cluster = cursor.fetchall()[0]
            cursor.execute("select * from %s where clusterid=%d"%(self.containerTable, clusterid))
            containers = cursor.fetchall()
            cluster['containers'] = containers
            ret = (True, cluster)
        return ret
    
    def get_all_clusters(self):
        ret = (False, 'error occurs when execute sql')
        with self.conn.cursor() as cursor:
            cursor.execute("select * from %s"%(self.clusterTable))
            ret = (True, cursor.fetchall())
        return ret


