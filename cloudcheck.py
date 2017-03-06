# This code is for noMadDrive running on the Amazon EC2
# Payap Sirinam
# Seshanth Rajagopalan
import os
from boto.s3.connection import S3Connection
import thread
import MySQLdb
import time
import tinys3
import sys
import hashlib
import hmac
import os
import random
from Crypto.Cipher import AES
import commands
from twilio.rest import TwilioRestClient

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
        # Send SMS to the user by using Twilio API
        message = client.messages.create(body="Your Data in S3 has been unauthorized modified, "
                                      "The nomad Drive service will be temporarily stopped",
                                    to="+16822192123",    # Replace with your phone number
                                    from_="+12675441568") # Replace with your Twilio number
        print message.sid
        sys.exit()

# Perform Decryption
def performDecryption(file, target, keyString):
    input = open(file,'rb')
    data = input.read()
    decryptedData = decrypt(data,key, keyString)

# Perform file synchronization periodically
def fileSyncronize(s3):
    while True:
        time.sleep(5)
        bucket = s3.get_bucket(bucket_name)
        tempFolder = os.getcwd()+'/filetemp/'
        if not os.path.exists(tempFolder):
            os.mkdir(tempFolde)

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

# Connect to S3
def connectS3():
    s3 = S3Connection(aws_access_key_id="AKIAIFLWKIJPFMLGITJQ",
                      aws_secret_access_key="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")
    return s3

# Connect to S3 storage
commands.getoutput('./clear')
print "Start monitoring unauthorized change on NOMAD drive...."
s3 = connectS3()

fileSyncronize(s3)
