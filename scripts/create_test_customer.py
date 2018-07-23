import argparse
import os

import psycopg2
import requests

class TestCustomer:
    """Container for customer specific info."""

     def __init__(self):
         self.customer_name = 'Test Customer'
         self.user_name = 'test_customer'
         self.email = 'test@example.com'
         self.password = 'str0ng!P@ss'
         self.provider_resource_name = 'arn:aws:iam::111111111111:role/CostManagement'
         self.bucket = 'test-bucket'
         self.provider_name = 'Test Provider'


class KokuCustomerOnboarder:
    """Uses the Koku API and SQL to create an onboarded customer."""

    def __init__(self, conn, host='localhost', port=80, admin='admin', password='pass'):
        self.conn = conn
        self.host = host
        self.port = port
        self.customer = TestCustomer()
        self.endpoint_base = f'http://{self.host}:{self.port}'
        self.token = self.get_token(admin, password)
        self.headers = {'Authorization': f'Token {self.token}'}

    def onboard(self):
        self.created_customer = self.create_customer()
        self.provider = self.create_provider()

    def get_token(self, user_name, password):
        endpoint = self.endpoint_base + '/api/v1/token-auth/'
        data = {'username': user_name , 'password': password}

        response = requests.post(endpoint, data=data)
        if response.status_code == 200:
            json_response = response.json()
            token = json_response.get('token')
            print(f'Acquired token {token}')
            return token
        else:
            raise Exception(f'{response.status_code}: {response.reason}')

    def create_customer(self):
        endpoint = self.endpoint_base + '/api/v1/customers/'
        data = {
            'name': self.customer.customer_name,
            'owner': {
                    'username': self.customer.user_name,
                    'email': self.customer.email,
                    'password': self.customer.password
            }
        }

        response = requests.post(
            endpoint,
            headers=self.headers,
            json=data
        )
        print(response.text)
        return response

    def create_provider(self):
        cursor = self.conn.cursor()
        auth_sql = """
            INSERT INTO api_providerauthentication (uuid, provider_resource_name)
                VALUES ('7e4ec31b-7ced-4a17-9f7e-f77e9efa8fd6', '{resource}')
            ;
        """.format(resource=self.customer.provider_resource_name)

        cursor.execute(auth_sql)
        print('Created provider authentication')

        billing_sql = """
            INSERT INTO api_providerbillingsource (uuid, bucket)
                VALUES ('75b17096-319a-45ec-92c1-18dbd5e78f94', '{bucket}')
            ;
        """.format(bucket=self.customer.bucket)

        cursor.execute(billing_sql)
        print('Created provider billing source')

        provider_sql = """
            INSERT INTO api_provider (uuid, name, type, authentication_id, billing_source_id, created_by_id, customer_id)
                VALUES('6e212746-484a-40cd-bba0-09a19d132d64', '{name}', 'AWS', 1, 1, 2, 1)
            ;
        """.format(name=self.customer.provider_name)

        cursor.execute(provider_sql)
        print('Created provider')

        self.conn.commit()


if __name__ == '__main__':
    default_api_host = os.getenv('KOKU_HOST', 'localhost')
    default_api_port = os.getenv('KOKU_PORT', '80')
    default_api_admin = os.getenv('KOKU_ADMIN', 'admin')
    default_api_pass = os.getenv('KOKU_PASSWORD', 'pass')

    default_db_host = os.getenv('POSTGRES_SQL_SERVICE_HOST', 'localhost')
    default_db_port = os.getenv('POSTGRES_SQL_SERVICE_PORT', '15432')
    default_db_name = os.getenv('DATABASE_NAME', 'koku')
    default_db_user = os.getenv('DATABASE_USER', 'postgres')
    default_db_pass = os.getenv('DATABASE_PASSWORD', '')

    parser = argparse.ArgumentParser()

    parser.add_argument('--api-host', dest='api_host', default=default_api_host)
    parser.add_argument('--api-port', dest='api_port', default=default_api_port)
    parser.add_argument('--api-admin', dest='api_admin', default=default_api_admin)
    parser.add_argument('--api-password', dest='api_password', default=default_api_pass)

    parser.add_argument('--db-host', dest='db_host', default=default_db_host)
    parser.add_argument('--db-port', dest='db_port', default=default_db_port)
    parser.add_argument('--db-database', dest='db_database', default=default_db_name)
    parser.add_argument('--db-user', dest='db_user', default=default_db_user)
    parser.add_argument('--db-password', dest='db_password', default=default_db_pass)

    args = vars(parser.parse_args())
    print(f'ARGS: {args}')

    db_args = {}
    for key, value in args.items():
        if key.startswith('db_'):
            db_args[key[3:]] = value

    conn = psycopg2.connect(**db_args)
    onboarder = KokuCustomerOnboarder(conn,
                                      host=args.get('api_host'),
                                      port=args.get('api_port'),
                                      admin=args.get('api_admin'),
                                      password=args.get('api_password'))
    onboarder.onboard()
    conn.close()
