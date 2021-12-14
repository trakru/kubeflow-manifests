import os

import pytest


from e2e.utils.constants import DEFAULT_USER_NAMESPACE
from e2e.utils.utils import wait_for, rand_name, WaitForCircuitBreakerError
from e2e.utils.config import metadata, configure_env_file

from e2e.conftest import region, get_accesskey, get_secretkey

from e2e.fixtures.cluster import cluster
from e2e.fixtures.kustomize import kustomize
from e2e.fixtures.clients import (
    kfp_client,
    port_forward,
    session_cookie,
    host,
    login,
    password,
    client_namespace,
    cfn_client,
    ec2_client
)

from e2e.utils.cloudformation_resources import create_cloudformation_fixture, get_stack_outputs
from e2e.utils.custom_resources import (
    create_katib_experiment_from_yaml,
    get_katib_experiment,
    delete_katib_experiment,
)

from kfp_server_api.exceptions import ApiException as KFPApiException
from kubernetes.client.exceptions import ApiException as K8sApiException

RDS_S3_KUSTOMIZE_MANIFEST_PATH = "../../examples/rds-s3/"
RDS_CLOUDFORMATION_TEMPLATE_PATH = "./cloudformation-templates/rds-s3.yaml"
CUSTOM_RESOURCE_TEMPLATES_FOLDER = "./resources/custom-resource-templates"


@pytest.fixture(scope="class")
def kustomize_path():
    return RDS_S3_KUSTOMIZE_MANIFEST_PATH


@pytest.fixture(scope="class")
def rds_stack(metadata, cluster, cfn_client, ec2_client, request):
    stack_name = rand_name("test-e2e-rds-stack-")

    resp = ec2_client.describe_vpcs(
        Filters=[
            {
                "Name": "tag:alpha.eksctl.io/cluster-name",
                "Values": [cluster],
            },
        ],
    )
    vpc_id = resp["Vpcs"][0]["VpcId"]

    resp = ec2_client.describe_subnets(
        Filters=[
            {
                "Name": "tag:alpha.eksctl.io/cluster-name",
                "Values": [cluster],
            },
            {
                "Name": "tag:aws:cloudformation:logical-id",
                "Values": ["SubnetPublic*"],
            },
        ],
    )
    public_subnets = [s["SubnetId"] for s in resp["Subnets"]]

    resp = ec2_client.describe_instances(
        Filters=[
            {
                "Name": "tag:eks:cluster-name",
                "Values": [cluster],
            }
        ],
    )
    instances = [i for r in resp["Reservations"] for i in r["Instances"]]
    security_groups = [i["SecurityGroups"][0]["GroupId"] for i in instances]

    return create_cloudformation_fixture(
        metadata=metadata,
        request=request,
        cfn_client=cfn_client,
        template_path=RDS_CLOUDFORMATION_TEMPLATE_PATH,
        stack_name=stack_name,
        metadata_key="test_rds_s3_cfn_stack",
        create_timeout=10 * 60,
        delete_timeout=10 * 60,
        params={
            "VpcId": vpc_id,
            "Subnets": ",".join(public_subnets),
            "SecurityGroupId": security_groups[0],
            "DBUsername": rand_name("admin"),
            "DBPassword": rand_name("Kubefl0w"),
        },
    )

KFP_MINIO_ARTIFACT_SECRET_PATCH_ENV_FILE = '../../apps/pipelines/minio-artifact-secret-patch.env'
KFP_PARAMS_ENV_FILE = '../../apps/pipelines/params.env'
KFP_SECRET_ENV_FILE = '../../apps/pipelines/secret.env'

KATIB_SECRETS_ENV_FILE = '../../apps/katib-external-db-with-kubeflow/secrets.env'

@pytest.fixture(scope="class")
def configure_manifests(cfn_client, rds_stack, region, request):
    stack_outputs = get_stack_outputs(cfn_client, rds_stack['stack_name'])

    configure_env_file(
        env_file_path=KFP_MINIO_ARTIFACT_SECRET_PATCH_ENV_FILE,
        env_dict={
            'accesskey': get_accesskey(request),
            'secretkey': get_secretkey(request),
        }
    )

    configure_env_file(
        env_file_path=KFP_PARAMS_ENV_FILE,
        env_dict={
            'dbHost': stack_outputs['RDSEndpoint'],
            'bucketName': stack_outputs['S3BucketName'],
            'minioServiceHost': 's3.amazonaws.com',
            'minioServiceRegion': region
        }
    )

    configure_env_file(
        env_file_path=KFP_SECRET_ENV_FILE,
        env_dict={
            'username': rds_stack['params']['DBUsername'],
            'password': rds_stack['params']['DBPassword'],
        }
    )

    configure_env_file(
        env_file_path=KATIB_SECRETS_ENV_FILE,
        env_dict={
            'KATIB_MYSQL_DB_DATABASE': 'kubeflow',
            'KATIB_MYSQL_DB_HOST': stack_outputs['RDSEndpoint'],
            'KATIB_MYSQL_DB_PORT': '3306',
            'DB_USER': rds_stack['params']['DBUsername'],
            'DB_PASSWORD': rds_stack['params']['DBPassword'],
        }
    )

PIPELINE_NAME = "[Demo] XGBoost - Iterative model training"
KATIB_EXPERIMENT_FILE = "katib-experiment-random.yaml"

# todo move this to util class
def wait_for_run_succeeded(kfp_client, run, job_name, pipeline_id):
    def callback():
        resp = kfp_client.get_run(run.id).run

        assert resp.name == job_name
        assert resp.pipeline_spec.pipeline_id == pipeline_id

        if 'Failed' == resp.status:
            print(resp)
            raise WaitForCircuitBreakerError('Pipeline run Failed')

        assert resp.status == "Succeeded"

    wait_for(callback)
class TestRDSS3():
    @pytest.fixture(scope="class")
    def setup(self, metadata, port_forward):
        metadata_file = metadata.to_file()
        print(metadata.params)  # These needed to be logged
        print("Created metadata file for TestRDSS3", metadata_file)

    def test_kfp_experiment(self, setup, kfp_client):
        name = rand_name("experiment-")
        description = rand_name("description-")
        experiment = kfp_client.create_experiment(
            name, description=description, namespace=DEFAULT_USER_NAMESPACE
        )

        assert name == experiment.name
        assert description == experiment.description
        assert DEFAULT_USER_NAMESPACE == experiment.resource_references[0].key.id

        resp = kfp_client.get_experiment(
            experiment_id=experiment.id, namespace=DEFAULT_USER_NAMESPACE
        )

        assert name == resp.name
        assert description == resp.description
        assert DEFAULT_USER_NAMESPACE == resp.resource_references[0].key.id

        kfp_client.delete_experiment(experiment.id)

        try:
            kfp_client.get_experiment(
                experiment_id=experiment.id, namespace=DEFAULT_USER_NAMESPACE
            )
            raise AssertionError("Expected KFPApiException Not Found")
        except KFPApiException as e:
            assert "Not Found" == e.reason

    def test_run_pipeline(self, setup, kfp_client):
        experiment_name = rand_name("experiment-")
        experiment_description = rand_name("description-")
        experiment = kfp_client.create_experiment(
            experiment_name,
            description=experiment_description,
            namespace=DEFAULT_USER_NAMESPACE,
        )

        pipeline_id = kfp_client.get_pipeline_id(PIPELINE_NAME)
        job_name = rand_name("run-")

        run = kfp_client.run_pipeline(
            experiment.id, job_name=job_name, pipeline_id=pipeline_id
        )

        assert run.name == job_name
        assert run.pipeline_spec.pipeline_id == pipeline_id
        assert run.status == None

        wait_for_run_succeeded(kfp_client, run, job_name, pipeline_id)

        kfp_client.delete_experiment(experiment.id)

    def test_katib_experiment(self, setup, cluster, region):
        filepath = os.path.abspath(
            os.path.join(CUSTOM_RESOURCE_TEMPLATES_FOLDER, KATIB_EXPERIMENT_FILE)
        )

        name = rand_name("katib-random-")
        namespace = DEFAULT_USER_NAMESPACE
        replacements = {"NAME": name, "NAMESPACE": namespace}

        resp = create_katib_experiment_from_yaml(
            cluster, region, filepath, namespace, replacements
        )

        assert resp["kind"] == "Experiment"
        assert resp["metadata"]["name"] == name
        assert resp["metadata"]["namespace"] == namespace

        resp = get_katib_experiment(cluster, region, namespace, name)

        assert resp["kind"] == "Experiment"
        assert resp["metadata"]["name"] == name
        assert resp["metadata"]["namespace"] == namespace

        resp = delete_katib_experiment(cluster, region, namespace, name)

        assert resp["kind"] == "Experiment"
        assert resp["metadata"]["name"] == name
        assert resp["metadata"]["namespace"] == namespace

        try:
            get_katib_experiment(cluster, region, namespace, name)
            raise AssertionError("Expected K8sApiException Not Found")
        except K8sApiException as e:
            assert "Not Found" == e.reason
