# Installation

Project Koku is divided into logical components. To achieve a fully
functional application, it requires the deployment of multiple
micro-applications.

The primary applications for Project Koku are:

- Koku API (Reporting and Query API service)
- Koku UI (Front-end Web UI)
- Masu (Data ingestion service)

For development and testing, Project Koku also includes:

- Nise (Test data generator)

This guide will focus on deploying Project Koku into an existing
[OpenShift](https://www.okd.io/) cluster.

## Deploying the Koku API

The Koku application contains two components - a web service and
database.

**Docker Compose**

The Koku API can also be deployed with Docker Compose with the following
steps:

- Create a Docker bridge network named `koku-network`:
    `docker network create koku-network`
- Set AWS credential environment variables: `AWS_SECRET_ACCESS_KEY`
    and `AWS_ACCESS_KEY_ID`
- Start koku server and database: `make docker-up`

This command will run database migraitons and start the API server. Once
complete the API server will be running on port 8000 on your localhost.

## Deploying the Koku UI

The Koku-UI application is the web-based frontend for Project Koku. It
is built using [Patternfly](https://www.patternfly.org/) and
[ReactJS](https://reactjs.org/).

Instructions for deploying the Koku UI can be found here:
<https://github.com/project-koku/koku-ui#getting-started>

## Deploying Masu

The Masu application contains several components: a web service,
message bus, and workers. Masu also uses the Koku database.
Configuration and management of the database are controlled from the
Koku API application.

Instructions for deploying Masu can be found here:
<https://github.com/project-koku/masu#getting-started>

Masu can alternatively be deployed with Docker Compose: Follow the steps
above to start the Koku API with Docker Compose

### Start masu services

Run `make docker-up`

To trigger Masu to process data, send a GET request to
`http://localhost:5042/api/cost-management/v1/download/`. You may want
to see Masu logs using `docker logs -f koku-worker`.
