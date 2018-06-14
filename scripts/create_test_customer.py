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

    def __init__(self, conn, host, port):
        self.conn = conn
        self.host = host
        self.port = port
        self.customer = TestCustomer()
        self.endpoint_base = f'http://{self.host}:{self.port}'
        self.token = self.get_token('admin', 'pass')
        self.headers = {'Authorization': f'Token {self.token}'}

    def onboard(self):
        self.created_customer = self.create_customer()
        self.provider = self.create_provider()

    def get_token(self, user_name, password):
        endpoint = self.endpoint_base + '/api/v1/token-auth/'
        data = {'username': user_name , 'password': password}
        token = requests.post(endpoint, data=data).json().get('token')
        print(f'Acquired token {token}')
        return token

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
    parser = argparse.ArgumentParser()
    parser.add_argument('host')
    parser.add_argument('port')
    args = vars(parser.parse_args())

    db_name = os.getenv('DATABASE_NAME')
    db_host = os.getenv('POSTGRES_SQL_SERVICE_HOST')
    db_port = os.getenv('POSTGRES_SQL_SERVICE_PORT')
    db_user = os.getenv('DATABASE_USER')
    db_password = os.getenv('DATABASE_PASSWORD')
    conn = psycopg2.connect(database=db_name, user=db_user,
                            password=db_password, port=db_port, host=db_host)

    onboarder = KokuCustomerOnboarder(conn, **args)
    onboarder.onboard()

    conn.close()
