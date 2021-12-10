import os

import pytest

from kfp_server_api.exceptions import ApiException as KFPApiException
from kubernetes.client.exceptions import ApiException as K8sApiException
from e2e.cloudformation_resources import create_cloudformation_fixture

from e2e.constants import GENERIC_KUSTOMIZE_MANIFEST_PATH, DEFAULT_USER_NAMESPACE, CUSTOM_RESOURCE_TEMPLATES_FOLDER
from e2e.utils import safe_open, wait_for, rand_name
from e2e.config import metadata, region
from e2e.cluster import cluster
# from e2e.kustomize import kustomize
# from e2e.clients import k8s_custom_objects_api_client, kfp_client, port_forward
from e2e.clients import cfn_client, ec2_client
# from e2e.custom_resources import create_katib_experiment_from_yaml, get_katib_experiment, delete_katib_experiment

RDS_S3_KUSTOMIZE_MANIFEST_PATH = './manifests/rds-s3/'

@pytest.fixture(scope="class")
def kustomize_path():
    return RDS_S3_KUSTOMIZE_MANIFEST_PATH

RDS_CLOUDFORMATION_TEMPLATE_PATH = './cloudformation-templates/rds.yaml'

@pytest.fixture
def rds_stack(metadata, cfn_client, ec2_client, request):
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
        template_path=RDS_S3_KUSTOMIZE_MANIFEST_PATH,
        stack_name=stack_name,
        metadata_key='test_rds_s3_cfn_stack',
        params={
            "VpcId": vpc_id,
            "Subnets": public_subnets,
            "SecurityGroupId": security_groups[:1],
            "DBUsername": rand_name('admin'),
            "DBPassword": rand_name('Kubefl0w'),
        }
    )


class TestRDSS3:
    @pytest.fixture(scope="class")
    def setup(self, metadata, cluster, rds_stack):
        metadata_file = metadata.to_file()
        print(metadata.params)  # These needed to be logged
        print("Created metadata file for TestRDSS3", metadata_file)

    def test_wow(self, setup):
        assert 1
