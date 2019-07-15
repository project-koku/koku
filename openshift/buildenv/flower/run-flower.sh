#!/bin/bash

# OAuth2 also requires these env vars:
# FLOWER_OAUTH2_KEY
# FLOWER_OAUTH2_SECRET
# FLOWER_OAUTH2_REDIRECT_URI
# FLOWER_OAUTH2_DOMAINS

case $FLOWER_AUTH_SCHEME in
    #### Basic Auth
    'basic')
        BASIC_AUTH="--basic_auth=${FLOWER_BASIC_AUTH_PARAMS}"
        AUTH_PARAMS=${BASIC_AUTH}
    ;;
    #### Google OAuth2
    'google')
        OAUTH2_PROVIDER="flower.views.auth.GoogleAuth2LoginHandler"
        OAUTH2_AUTH="--auth=${FLOWER_OAUTH2_DOMAINS} --auth_provider=${OAUTH2_PROVIDER}"
        AUTH_PARAMS=${OAUTH2_AUTH}
    ;;
    #### Github OAuth2
    'github')
        OAUTH2_PROVIDER="flower.views.auth.GithubLoginHandler"
        OAUTH2_AUTH="--auth=${OAUTH2_DOMAINS} --auth_provider=${OAUTH2_PROVIDER}"
        AUTH_PARAMS=${OAUTH2_AUTH}
    ;;
    #### No auth (danger!)
    *)
        echo "WARNING: no auth configured!"
        AUTH_PARAMS=""
    ;;
esac

# run flower
BROKER="amqp://${RABBITMQ_HOST:-localhost}:5672//"
PYTHONPATH=. scl enable rh-python36 -- flower --broker=${BROKER} ${AUTH_PARAMS}
