import os

import pytest


from e2e.utils.constants import DEFAULT_USER_NAMESPACE
from e2e.utils.utils import wait_for, rand_name
from e2e.utils.config import metadata

from e2e.conftest import region

from e2e.fixtures.cluster import cluster
from e2e.fixtures.kustomize import kustomize
from e2e.fixtures.clients import cfn_client, ec2_client

from e2e.utils.cloudformation_resources import create_cloudformation_fixture

from kfp_server_api.exceptions import ApiException as KFPApiException
from kubernetes.client.exceptions import ApiException as K8sApiException

RDS_S3_KUSTOMIZE_MANIFEST_PATH = "../../examples/rds-s3/"
RDS_CLOUDFORMATION_TEMPLATE_PATH = './cloudformation-templates/rds.yaml'

@pytest.fixture(scope="class")
def kustomize_path():
    return RDS_S3_KUSTOMIZE_MANIFEST_PATH

@pytest.fixture(scope="class")
def rds_stack(metadata, cluster, cfn_client, ec2_client, request):
    stack_name = rand_name('test-e2e-rds-stack-')

    resp = ec2_client.describe_vpcs(
        Filters=[
            {
                'Name': 'tag:alpha.eksctl.io/cluster-name',
                'Values': [cluster],
            },
        ],
    )
    vpc_id = resp['Vpcs'][0]['VpcId']

    resp = ec2_client.describe_subnets(
        Filters=[
            {
                'Name': 'tag:alpha.eksctl.io/cluster-name',
                'Values': [cluster],
            },
            {
                'Name': 'tag:aws:cloudformation:logical-id',
                'Values': ["SubnetPublic*"],
            },
        ],
    )
    public_subnets = [s['SubnetId'] for s in resp['Subnets']]


    resp = ec2_client.describe_instances(
        Filters=[
            {
                'Name': 'tag:eks:cluster-name',
                'Values': [cluster],
            }
        ],
    )
    instances = [i for r in resp['Reservations'] for i in r['Instances']]
    security_groups = [i['SecurityGroups'][0]['GroupId'] for i in instances]

    return create_cloudformation_fixture(
        metadata=metadata,
        request=request,
        cfn_client=cfn_client,
        template_path=RDS_CLOUDFORMATION_TEMPLATE_PATH,
        stack_name=stack_name,
        metadata_key='test_rds_s3_cfn_stack',
        create_timeout=10*60,
        delete_timeout=10*60,
        params={
            "VpcId": vpc_id,
            "Subnets": ','.join(public_subnets),
            "SecurityGroupId": security_groups[0],
            "DBUsername": rand_name('admin'),
            "DBPassword": rand_name('Kubefl0w'),
        }
    )


class TestRDSS3:
    @pytest.fixture(scope="class")
    def setup(self, metadata, rds_stack):
        metadata_file = metadata.to_file()
        print(metadata.params)  # These needed to be logged
        print("Created metadata file for TestRDSS3", metadata_file)

    def test_wow(self, setup):
        assert 1
