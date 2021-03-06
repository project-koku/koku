#!/bin/bash
function importCert() {
PEM_FILE=$1
PASSWORD=$2
KEYSTORE=$3
# number of certs in the PEM file
CERTS=$(grep 'END CERTIFICATE' $PEM_FILE| wc -l)

# For every cert in the PEM file, extract it and import into the JKS keystore
# awk command: step 1, if line is in the desired cert, print the line
#              step 2, increment counter when last line of cert is found
for N in $(seq 0 $(($CERTS - 1))); do
    ALIAS="${PEM_FILE%.*}-$N"
    cat $PEM_FILE |
    awk "n==$N { print }; /END CERTIFICATE/ { n++ }" |
    keytool -noprompt -import -trustcacerts \
            -alias $ALIAS -keystore $KEYSTORE -storepass $PASSWORD
done
}
set -e

# always add the openshift service-ca.crt if it exists
if [ -a /var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt ]; then
echo "Adding /var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt to $JAVA_HOME/lib/security/cacerts"
importCert /var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt changeit $JAVA_HOME/lib/security/cacerts
fi

# add node id to node config
NODE_CONFIG="${PRESTO_HOME}/etc/node.properties"
# ensure there's a newline between the last item in the config and what we add
echo "" >> $NODE_CONFIG
if ! grep -q -F 'node.id' "$NODE_CONFIG"; then
NODE_ID="node.id=$MY_NODE_ID"
echo "Adding $NODE_ID to $NODE_CONFIG"
echo "$NODE_ID" >> "$NODE_CONFIG"
fi

# add AWS creds to hive catalog properties
HIVE_CATALOG_CONFIG="${PRESTO_HOME}/etc/catalog/hive.properties"
# ensure there's a newline between the last item in the config and what we add
echo "" >> $HIVE_CATALOG_CONFIG
if ! grep -q -F 'hive.s3.aws-access-key' "$HIVE_CATALOG_CONFIG"; then
echo "Adding hive.s3.aws-access-key and hive.s3.aws-secret-key to $HIVE_CATALOG_CONFIG"
echo "hive.s3.aws-access-key=$AWS_ACCESS_KEY_ID" >> "$HIVE_CATALOG_CONFIG"
echo "hive.s3.aws-secret-key=$AWS_SECRET_ACCESS_KEY" >> "$HIVE_CATALOG_CONFIG"
echo "hive.s3.endpoint=$S3_ENDPOINT" >> "$HIVE_CATALOG_CONFIG"
echo "hive.s3.ssl.enabled=false" >> "$HIVE_CATALOG_CONFIG"
echo "hive.s3.path-style-access=true" >> "$HIVE_CATALOG_CONFIG"

fi

# add UID to /etc/passwd if missing
if ! whoami &> /dev/null; then
    if test -w /etc/passwd || stat -c "%a" /etc/passwd | grep -qE '.[267].'; then
        echo "Adding user ${USER_NAME:-presto} with current UID $(id -u) to /etc/passwd"
        # Remove existing entry with user first.
        # cannot use sed -i because we do not have permission to write new
        # files into /etc
        sed  "/${USER_NAME:-presto}:x/d" /etc/passwd > /tmp/passwd
        # add our user with our current user ID into passwd
        echo "${USER_NAME:-presto}:x:$(id -u):0:${USER_NAME:-presto} user:${HOME}:/sbin/nologin" >> /tmp/passwd
        # overwrite existing contents with new contents (cannot replace the
        # file due to permissions)
        cat /tmp/passwd > /etc/passwd
        rm /tmp/passwd
    fi
fi

exec "$@"
