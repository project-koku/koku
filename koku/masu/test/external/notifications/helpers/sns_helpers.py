#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

sns_subscription_confirm_headers = [
    (
        'X-Amz-Sns-Topic-Arn',
        'arn:aws:sns:us-east-1:589179999999:CostUsageNotificationDemo',
    ),
    ('X-Amz-Sns-Message-Type', 'SubscriptionConfirmation'),
    ('X-Amz-Sns-Message-Id', '010b7c42-3f24-4865-83b1-13120d79466b'),
    (
        'X-Amz-Sns-Subscription-Arn',
        'arn:aws:sns:us-east-1:123456789012:MyTopic:2bcfbf39-05c3-41de-beaa-fcfcc21c8f55',
    ),
    ('Content-Length', 1637),
    ('Content-Type', 'text/plain; charset=UTF-8'),
    ('Host', 'masu.net:6868'),
    ('Connection', 'Keep-Alive'),
    ('User-Agent', 'Amazon Simple Notification Service Agent'),
    ('Accept-Encoding', 'gzip,deflate'),
]

sns_subscription_confirm_body_dict = {
    'Type': 'SubscriptionConfirmation',
    'MessageId': '010b7c42-3f24-4865-83b1-13120d79466b',
    'Token': '2336412f37fb687f5d51e6e241da92fd72d769c811cb257f2ca8bbb9e329dd2eb427b0935ce7fe84f91e14e5994d2d9039b3aade5b4f16dd5ab3979b05751962ceed2c7e193e7b7797630c31eec29477949064522feb104a311b44e1268ba7bdfdc06d7e6f39174dbb69326a379d06cbbc96adcdc24939e36892e024aa0e96d2',
    'TopicArn': 'arn:aws:sns:us-east-1:589179999999:CostUsageNotificationDemo',
    'Message': 'You have chosen to subscribe to the topic arn:aws:sns:us-east-1:589179999999:CostUsageNotificationDemo.\nTo confirm the subscriptionDataBuilder, visit the SubscribeURL included in this message.',
    'SubscribeURL': 'https://sns.us-east-1.amazonaws.com/?Action=ConfirmSubscription&TopicArn=arn:aws:sns:us-east-1:589179999999:CostUsageNotificationDemo&Token=2336412f37fb687f5d51e6e241da92fd72d769c811cb257f2ca8bbb9e329dd2eb427b0935ce7fe84f91e14e5994d2d9039b3aade5b4f16dd5ab3979b05751962ceed2c7e193e7b7797630c31eec29477949064522feb104a311b44e1268ba7bdfdc06d7e6f39174dbb69326a379d06cbbc96adcdc24939e36892e024aa0e96d2',
    'Timestamp': '2018-07-05T12:29:27.641Z',
    'SignatureVersion': '1',
    'Signature': 'L8VmRMT55sv326Rt1HBawA8hPKR0plaBfvI8hlZNm2nhaMkVzvFkvKiMZucfQ7bYWaYqVF+xzvqkaRnMw8/uC4QcrM5DK5HcXYfAJCeI8t32jTg3Kcdn3SGBiyxcBWYt8qSXL7403ho4vIVpCHRuX6K2ZydS7sxx6umr/nanaOUGnkDeC91GFoUMslNw7yITc0YunPwg8GcvKgLhsQr2d7C5I3zDprA+Ds29voLN6v66hH0uR0LEfDq9Ky0Dgii4UebYUgKBCWSy5ETsRHqug5tPNzv9afexjdXrjEUYbvYZO+RRDPztwGjyHw6CL35B85FLZ7UDPLeRysZq47gb+Q==',
    'SigningCertURL': 'https://sns.us-east-1.amazonaws.com/SimpleNotificationService-eaea6120e66ea12e88dcd8bcbddca752.pem',
}

sns_notification_headers = [
    ('X-Amz-Sns-Message-Type', 'Notification'),
    ('X-Amz-Sns-Message-Id', 'da41e39f-ea4d-435a-b922-c6aae3915ebe'),
    ('X-Amz-Sns-Topic-Arn', 'arn:aws:sns:us-east-1:123456789012:MyTopic'),
    (
        'X-Amz-Sns-Subscription-Arn',
        'arn:aws:sns:us-east-1:123456789012:MyTopic:2bcfbf39-05c3-41de-beaa-fcfcc21c8f55',
    ),
    ('Content-Length', 761),
    ('Content-Type', 'text/plain; charset=UTF-8'),
    ('Host', 'ec2-50-17-44-49.compute-1.amazonaws.com'),
    ('Connection', 'Keep-Alive'),
    ('User-Agent', 'Amazon Simple Notification Service Agent'),
]

sns_notification_body_dict = {
    'Type': 'Notification',
    'MessageId': '879e9da4-a9ca-5eec-a13b-ce13a7b32b43',
    'TopicArn': 'arn:aws:sns:us-east-1:589179999999:CostUsageReportUpdateTopic',
    'Subject': 'Amazon S3 Notification',
    'Message': '{"Records":[{"eventVersion":"2.0","eventSource":"aws:s3","awsRegion":"us-east-1","eventTime":"2018-07-04T18:04:41.786Z","eventName":"ObjectCreated:Put","userIdentity":{"principalId":"AWS:AIDAJLSI7DTYBUZAOKHVM"},"requestParameters":{"sourceIPAddress":"10.88.30.162"},"responseElements":{"x-amz-request-id":"DBC59DCBEE8AB006","x-amz-id-2":"4MUgFYLBTnbinBcBSax8FIykKKvLinL6IBZYYGNt0267L7/WixNzuupAM1OtpMmua+DoV/guVYU="},"s3":{"s3SchemaVersion":"1.0","configurationId":"CostUsageNotification","bucket":{"name":"cost-usage-bucket","ownerIdentity":{"principalId":"A2V75OLLZ1ABF7"},"arn":"arn:aws:s3:::cost-usage-bucket"},"object":{"key":"/koku/20180701-20180801/koku-Manifest.json","size":6518,"eTag":"963195a6fa85a9b98a1f93a981a805fd","sequencer":"005B3D0C39C106E6AC"}}}]}',
    'Timestamp': '2018-07-04T18:04:41.820Z',
    'SignatureVersion': '1',
    'Signature': 'mDniwbH0VTvDtm4VaZf66Ox3joxBv92lJb4KXEqq1AeVKTfpyCuB5XROU7iw4v2AD97DPr/C9tHIOuuMaDANJxVLor7TfJB7xCA9PYg3963NqCE1uvl5fv7NYhCpl4bhGwKwKBIYvOvWbVxcAQilRWZHDmLAqEmWfzCIPtACWc9xAt0rbL2Zk0TqAhU87QU3dAX63bV6HdNOHMCp1xS5bNVWWWJ09vsUNwSVS4zQ/bAxymffoAMyIEBKlCU8le4khjGlmSIX6S6vsl0rVd9e8hInSmAHN4mcBE7SUz/TrlmwwejP6ysEdHRnHfU41/axMxBZyfH654A2Kne6Vs01mg==',
    'SigningCertURL': 'https://sns.us-east-1.amazonaws.com/SimpleNotificationService-eaea6120e66ea12e88dcd8bcbddca752.pem',
    'UnsubscribeURL': 'https://sns.us-east-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:us-east-1:589179999999:CostUsageReportUpdateTopic:7d549a1b-502f-47f7-9469-9ed18671e76a',
}


def modify_header_list(header_list, key, new_value=None):
    new_header_list = header_list
    for idx, header in enumerate(new_header_list):
        if key == header[0]:
            if new_value is None:
                new_header_list.remove(header)
            else:
                new_header_list[idx] = (key, new_value)
    return new_header_list
