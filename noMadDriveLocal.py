# This code is for noMadDrive running on the user's computer
# Payap Sirinam
# Seshanth Rajagopalan 

import os
from boto.s3.connection import S3Connection, Bucket, Key
import thread
import MySQLdb
import time
import tinys3
import sys
import hashlib
import hmac
import os
import random
from time import gmtime, strftime
from Crypto.Cipher import AES

from twilio.rest import TwilioRestClient
global lock
lock = 0
# Your Account Sid and Auth Token from twilio.com/user/account
account_sid = "ACf1cd4686596ca2e93f81bfaa366ce349"
auth_token  = "c50f329ddce70c0cf85fc5e2a9461ff3"
client = TwilioRestClient(account_sid, auth_token)

AES_BLOCK_SIZE = 32
SIG_SIZE = hashlib.sha256().digest_size
key = "LoveyoufromPayap"

""" Initial Necessary Variables """
# Secure drive name
secureDrivename = "NomadDrive"
# Checking our current directory
currentHome = os.getenv("HOME")
# Secure folder location
expectedDirectory = currentHome + '/' + secureDrivename
bucket_name = 'nomaddrive'

# Match HMAC
def decrypt(data,key, keyString):
    ## extract the hash
    sig = data[-SIG_SIZE:]
    data = data[:-SIG_SIZE]
    ## check the encrypted data is valid using the hmac hash
    if hmac.new(key, data, hashlib.sha256).digest() != sig:
        errorlog = currentHome+'/error.log'
        filelog = open(errorlog, 'w')
        logmess = "Your Data %s in S3 has been unauthorized modified"%keyString
        filelog.write(logmess)
        filelog.close()
        message = client.messages.create(body="Your Data in S3 has been unauthorized modified, "
                                      "The nomad Drive service will be temporarily stopped",
                                    to="+16822192123",    # Replace with your phone number
                                    from_="+12675441568") # Replace with your Twilio number
        print message.sid
	raise SystemExit()
        sys.exit()
    else:
        ## extract the initialisation vector
        iv = data[:16]
        data = data[16:]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        ## decrypt
        data = cipher.decrypt(data)
        ## remove the padding
        return data[:-ord(data[-1])]

# Perform Decryption
def performDecryption(file, target, keyString):
    input = open(file,'rb')
    data = input.read()
    decryptedData = decrypt(data,key, keyString)
    print "successfully decrypted to ", target,strftime("%Y-%m-%d %H:%M:%S", gmtime())
    output = open(target,'wb')
    output.write(decryptedData)
    output.close()

# Encryption + HMAC
def encrypt(data,key):
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ## get the required padding length
    pad = AES_BLOCK_SIZE - len(data) % AES_BLOCK_SIZE
    ## pad the data by appending repeate char
    data = data + pad * chr(pad)
    ## encrypt and prepend the initialisation vector
    data = iv + cipher.encrypt(data)
    ## hash the encrypted data
    sig = hmac.new(key, data, hashlib.sha256).digest()
    ## append the hash to the data
    return data + sig

# Start encryption
def performEncryption(file,s3):
    input = open(file,'rb')
    data = input.read()
    input.close()
    encryptedData = encrypt(data,key)
    hiddenEnc = currentHome+"/.temp.encrypted"
    output = open(hiddenEnc,'wb')
    output.write(encryptedData)
    output.close()
    conn = tinys3.Connection("AKIAIFLWKIJPFMLGITJQ","ljKobD3usDRj6VWZpH+bHQZzZPlU8mMm7PlooOx7")
    f = open(hiddenEnc,'rb')
    uploadFile = file[len(expectedDirectory):]
    conn.upload(uploadFile,f,bucket_name)
    print "upload successfully",uploadFile,strftime("%Y-%m-%d %H:%M:%S", gmtime())
    os.remove(hiddenEnc)

# Generate hash value of a file with SHA-256
def genateHash(file):
    BLOCKSIZE = 65536
    hasher = hashlib.sha256()
    with open(file, 'rb') as afile:
        buf = afile.read(BLOCKSIZE)
        while len(buf) > 0:
            hasher.update(buf)
            buf = afile.read(BLOCKSIZE)
    hashvalue = hasher.hexdigest()
    return hashvalue

def updateHashRDS(db, pointer, data, hashedValue, lastModifiedlocal, insertTime):
    pointer = db.cursor()
    filename = data
    sql = "UPDATE fileinfo SET HASHVALUE = %s WHERE FILENAME = %s"
    args=(hashedValue, filename)
    pointer.execute(sql,args)
    db.commit()
    pointer = db.cursor()
    sql = "UPDATE fileinfo SET LASTMODIFIED = %s WHERE FILENAME = %s"
    args=(lastModifiedlocal, filename)
    pointer.execute(sql,args)
    db.commit()
    pointer = db.cursor()
    sql = "UPDATE fileinfo SET INSERTTIME = %s WHERE FILENAME = %s"
    args=(insertTime, filename)
    pointer.execute(sql,args)
    db.commit()
    print "Update database"

# OS walkthrough the directory and sub directory to list all files
def osWalkthrough(expectedDirectory):
    listofFile = list()
    for dirPath, dirs, files in os.walk(expectedDirectory):
        for fileName in files:
            fname = os.path.join(dirPath,fileName)
            if fname[-1:] != '~':
                listofFile.append(fname)
    return listofFile

# Check anything changed in the folder
def checkChange(expectedDirectory,db,s3, previousList):
    while True:
        time.sleep(5)
        # Perform OS walktrough
        listofFile = osWalkthrough(expectedDirectory)
        # Check whether there is a new file or a modified file or not
        for file in listofFile:
            pointer = db.cursor()
            # check whether there is this file in database or not
            sql = "SELECT * from fileinfo WHERE FILENAME=%s"
            args=(file[len(expectedDirectory):],)
            pointer.execute(sql,args)
            db.commit()
            data=pointer.fetchall()
            if len(data) == 0: #There is no file
                # Encrypt and upload the file to S3
                performEncryption(file, s3)
                #Insert this file info along with hash value to the database
                hashedValue = genateHash(file)
                sql = "INSERT INTO fileinfo VALUES (%s, %s, %s, %s)"
                statinfo = os.stat(file)
                lastModified = float(statinfo.st_mtime)
                args=(file[len(expectedDirectory):], hashedValue, lastModified, str(time.time()))
                pointer.execute(sql,args)
                db.commit()
            else: # there is a file, then check whether it is modified or not
                hashedValue = genateHash(file)
                try:
                    sql = "SELECT * from fileinfo WHERE FILENAME=%s"
                    args=(file[len(expectedDirectory):],)
                    pointer.execute(sql,args)
                    data=pointer.fetchall()
                    originHash = data[0][1]
                    remotelastModified = data[0][3]
                    statinfo = os.stat(file)
                    lastModifiedlocal = float(statinfo.st_mtime)
                    # If there is something change
                    if (float(remotelastModified) - float(lastModifiedlocal)) < -2.0 and hashedValue != originHash :
                        print remotelastModified, lastModifiedlocal, (float(remotelastModified) - float(lastModifiedlocal))
                        # The local file is newer than the remote file
                        # upload new file
                        print "Local file is newer than the remote file ",strftime("%Y-%m-%d %H:%M:%S", gmtime())
                        performEncryption(file,s3)
                        # update database
                        updateHashRDS(db, pointer, data[0][0], hashedValue, lastModifiedlocal, time.time())
                    elif (float(remotelastModified) - float(lastModifiedlocal)) > 2.0 and hashedValue != originHash :
                        # The local file is older than the remote file
                        print "The local file is older than the remote file ",strftime("%Y-%m-%d %H:%M:%S", gmtime())
                        bucket = s3.get_bucket(bucket_name)
                        tempFolder = os.getcwd()+'/filetemp/'
                        bucket_list = bucket.list()
                        for l in bucket_list:
                            keyString = str(l.key)
                            d = tempFolder + keyString
                            try:
                                l.get_contents_to_filename(d)
                                # perform decryption
                                cur = os.getcwd()+'/filetemp'
                                target = expectedDirectory+d[len(cur):]
                                performDecryption(d, target, keyString)
                                os.remove(d)
                            except OSError:
                                # check if dir exists
                                if not os.path.exists(d):
                                    os.mkdir(d)
                except:pass
        # Then check adding new file
        currentFilelist = osWalkthrough(expectedDirectory)
        newFile = list(set(currentFilelist) - set(previousList))
        if len(newFile) > 0:
            # there is new file
            for new in newFile:
                # check whether the new files is the file just deleted from the other server
                newFilepath = new[len(expectedDirectory):]
                sql = "SELECT * FROM delfile WHERE FILENAME=%s"
                args=(newFilepath,)
                pointer.execute(sql,args)
                db.commit()
                data=pointer.fetchall()
                print data

                if len(data) > 0:
                    timeDelete = float(data[0][1])
                    if time.time() - timeDelete > 20:
                        print "There is a new file in local machine",strftime("%Y-%m-%d %H:%M:%S", gmtime())
                        # uploading new files
                        file = new
                        performEncryption(file, s3)
                        #Insert this file info along with hash value to the database
                        hashedValue = genateHash(file)
                        statinfo = os.stat(file)
                        lastModified = float(statinfo.st_mtime)
                        updateHashRDS(db, pointer, file[len(expectedDirectory):], lastModified, lastModifiedlocal, time.time())
                        currentFilelist = osWalkthrough(expectedDirectory)
                        previousList = currentFilelist
        # Check removing files
        removeFile = list(set(previousList) - set(currentFilelist))
        if len(removeFile) > 0:
            for rem in removeFile:
                # remotely remove file
                print "There is a removed file in local machine",strftime("%Y-%m-%d %H:%M:%S", gmtime())
                b = Bucket(s3, bucket_name)
                k = Key(b)
                removeFilepath = rem[len(expectedDirectory):]
                k.key = removeFilepath
                b.delete_key(k)
                sql = "SELECT * FROM delfile WHERE FILENAME=%s"
                args=(removeFilepath,)
                pointer.execute(sql,args)
                db.commit()
                data=pointer.fetchall()
                if len(data) > 0:
                    sql = "UPDATE delfile SET DELTIME = %s WHERE FILENAME = %s"
                    args=(str(time.time()),removeFilepath)
                    pointer.execute(sql,args)
                    db.commit()
                else:
                    sql = "INSERT INTO delfile VALUES (%s, %s)"
                    args=(removeFilepath, str(time.time()))
                    pointer.execute(sql,args)
                    db.commit()
                sql = "DELETE FROM fileinfo WHERE FILENAME=%s"
                args=(removeFilepath,)
                pointer.execute(sql,args)
                db.commit()
        previousList = currentFilelist
        # Check remote remove
        pointer = db.cursor()
        # check whether there is this file in database or not
        sql = "SELECT * from fileinfo"
        args=[]
        pointer.execute(sql,args)
        data=pointer.fetchall()
        currentRemote = list()
        db.commit()
        print data
        for i in data:
            remoteDir = expectedDirectory+i[0]
            currentRemote.append(remoteDir)
        currentStatus = previousList
        print "Update status: ",strftime("%Y-%m-%d %H:%M:%S", gmtime())
        print "Current Local Files : ", currentStatus
        print "Current Remote Files : ", currentRemote

        removeFilecheck = list(set(currentStatus)-set(currentRemote))
        if len(removeFilecheck) > 0:
            # There is a remotely removed file, need to update with remote file
            for r in removeFilecheck:
                print "There is a removed file in remote server",strftime("%Y-%m-%d %H:%M:%S", gmtime())
                try:
                    os.remove(r)
                except: pass
        previousList = currentRemote

# Connect to S3
def connectS3():
    s3 = S3Connection(aws_access_key_id="AKIAIFLWKIJPFMLGITJQ",
                      aws_secret_access_key="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")
    return s3

# Connect to Database
def connectRDS():
    # Access to RDS SQL Database on AWS
    aws_endpoint = "assignment4.ckbendgp9tbe.us-east-1.rds.amazonaws.com"
    username = "payap"
    password = "isecpayap"
    db_name = "nomad"

    db = MySQLdb.connect(host=aws_endpoint, # your aws host
                     user=username,     # your username
                     passwd=password,   # your password
                     db=db_name         # name of the data base
                    )
    db.autocommit(True)
    return db

# In case use this at the first time
def preSetup(secureDrivename, expectedDirectory):
    if not os.path.exists(expectedDirectory):
        os.makedirs(expectedDirectory)
        print "Secure Drive was sucessfully created at %s"%expectedDirectory ,strftime("%Y-%m-%d %H:%M:%S", gmtime())

# Syncronizing with S3 at the first time
def firstSyncronize(s3):
    print "First synchronize"
    bucket = s3.get_bucket(bucket_name)
    tempFolder = os.getcwd()+'/filetemp/'
    bucket_list = bucket.list()
    for l in bucket_list:
        keyString = str(l.key)
        d = tempFolder + keyString
        try:
            l.get_contents_to_filename(d)
            # perform decryption
            cur = os.getcwd()+'/filetemp'
            print cur
            target = expectedDirectory+d[len(cur):]
            print target
            performDecryption(d, target, keyString)
            os.remove(d)
        except OSError:
            # check if dir exists
            if not os.path.exists(d):
                os.mkdir(d)

# Perform file synchronization periodically
def fileSyncronize(s3):
    while True:
        time.sleep(60)
        if lock == 0:
            bucket = s3.get_bucket(bucket_name)
            tempFolder = os.getcwd()+'/filetemp/'
            bucket_list = bucket.list()
            for l in bucket_list:
                keyString = str(l.key)
                d = tempFolder + keyString
                try:
                    l.get_contents_to_filename(d)
                    # perform decryption
                    cur = os.getcwd()+'/filetemp'
                    target = expectedDirectory+d[len(cur):]
                    performDecryption(d, target, keyString)
                    os.remove(d)
                except OSError:
                    # check if dir exists
                    if not os.path.exists(d):
                        os.mkdir(d)

# Connect to S3 storage
s3 = connectS3()
# Check whether the NomadDrive is existed
preSetup(secureDrivename, expectedDirectory)
# Connect to DB
db = connectRDS()
firstSyncronize(s3)
previousList = osWalkthrough(expectedDirectory)

# Perform checkChange to detect any change in nomad folder
try:
    thread.start_new_thread( fileSyncronize, (s3, ) )
    thread.start_new_thread( checkChange, (expectedDirectory,db,s3, previousList) )

except:
   print "Error: unable to start thread",strftime("%Y-%m-%d %H:%M:%S", gmtime())
while True:
    time.sleep(10)

db.close()
