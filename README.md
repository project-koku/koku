# SaltCellar

### Getting Started

To deploy a new app on OpenShift Container Platform:

```
git clone https://github.com/SaltCellar/SaltCellar
cd SaltCellar
oc new-app openshift/templates/django-postgresql-persistent.json --code=https://github.com/SaltCellar/SaltCellar
```

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)
