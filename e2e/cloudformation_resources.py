import boto3
from e2e.config import configure_resource_fixture
from utils import rand_name

def create_stack(cfn_client, template_path, stack_name, params={}, capabilities=[], timeout=300, interval=10):
    with open(template_path) as file:
        body = file.read()

    stack_params = [
        {
            'ParameterKey': key,
            'ParameterValue': value,
            'UsePreviousValue': False
        } for key, value in params.items()
    ]

    resp = cfn_client.create_stack(
        StackName=stack_name,
        TemplateBody=body,
        Parameters=stack_params,
        Capabilities=capabilities
    )

    stack_id = resp['StackId']

    print(f"Creating stack {stack_name}, waiting for stack create complete")
    waiter = cfn_client.get_waiter('stack_create_complete')
    waiter.wait(
        StackName=stack_name,
        WaiterConfig={
            'Delay': interval,
            'MaxAttempts': timeout // interval + 1
        }
    )

    return stack_name, stack_id


def delete_stack(cfn_client, stack_name, timeout=300, interval=10):
    cfn_client.delete_stack(
        StackName=stack_name
    )

    print(f"Deleting stack {stack_name}, waiting for stack delete complete")
    waiter = cfn_client.get_waiter('stack_delete_complete')
    waiter.wait(
        StackName=stack_name,
        WaiterConfig={
            'Delay': interval,
            'MaxAttempts': timeout // interval + 1
        }
    )

def create_cloudformation_fixture(metadata,
                                  request,
                                  cfn_client,
                                  template_path,
                                  stack_name,
                                  metadata_key,
                                  params={},
                                  capabilities=[],
                                  create_timeout=300,
                                  create_interval=10,
                                  delete_timeout=300,
                                  delete_interval=10):
    
    def on_create():
        create_stack(cfn_client=cfn_client,
                     template_path=template_path,
                     stack_name=stack_name,
                     params=params,
                     capabilities=capabilities,
                     timeout=create_timeout,
                     interval=create_interval)
    
    def on_delete():
        name = metadata.get(metadata_key) or stack_name
        delete_stack(cfn_client=cfn_client,
                     stack_name=name,
                     timeout=delete_timeout,
                     interval=delete_interval)
    
    resource_details = {
        stack_name: stack_name,
        params: params
    }

    return configure_resource_fixture(metadata=metadata,
                                      request=request,
                                      resource_details=resource_details,
                                      metadata_key=metadata_key,
                                      on_create=on_create,
                                      on_delete=on_delete)
    
    


if __name__ == '__main__':
    path = './cloudformation-templates/test.yaml'

    client = boto3.client('cloudformation', region_name='us-west-1')

    params = {
        "ClusterName": rand_name("blah-")
    }

    name, id = create_stack(client, path, 'wowee-', params=params)
    print(name, id)

    delete_stack(client, name)
    print('deleted', name)

