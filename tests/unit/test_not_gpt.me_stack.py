import aws_cdk as core
import aws_cdk.assertions as assertions

from not_gpt.me.not_gpt.me_stack import NotGptMeStack

# example tests. To run these tests, uncomment this file along with the example
# resource in not_gpt.me/not_gpt.me_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = NotGptMeStack(app, "not-gpt-me")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
