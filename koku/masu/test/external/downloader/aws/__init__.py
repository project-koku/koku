"""AWS downloader tests."""
import random
import string

import faker


def fake_aws_account_id():
    """Generate a dummy AWS AwsAccount ID for testing purposes."""
    return "".join(random.choice(string.digits) for _ in range(12))


def fake_arn(account_id="", service="fakeservice", region="", resource_separator=":", generate_account_id=False):
    """
    Generate a dummy AWS ARN for testing purposes.

    account_id argument is optional, and will be randomly generated if None.
    Args:
        account_id (str): Optional account ID.
        service (str): Optional service name
        region (str): Optional region
        resource_separator (str): A colon ':' or a forward-slash '/'
        generate_account_id (bool): Whether to generate a random account_id,
                        This will override any account_id that is passed in
    Returns:
        str: A well-formed, randomized ARN.

    """
    if generate_account_id:
        account_id = fake_aws_account_id()
    resource = faker.Faker().name()
    resource_type = faker.Faker().name().replace(" ", "_")
    arn = ("arn:aws:{}:{}:{}:{}{}{}").format(service, region, account_id, resource_type, resource_separator, resource)
    return arn
