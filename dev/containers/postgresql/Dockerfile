from postgres:15

ARG USER_ID=999
ARG GROUP_ID=999

COPY 99_postgresql_conf.sh docker-entrypoint-initdb.d/

RUN groupmod -o -g ${GROUP_ID} postgres
RUN usermod -o -u ${USER_ID} -g ${GROUP_ID} postgres
