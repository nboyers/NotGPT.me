import aws_cdk as core
import aws_cdk.assertions as assertions

from cdk.HumanToneStack import HumanToneStack

def test_stack_synth():
    app = core.App()
    stack = HumanToneStack(app, "humantone-test")
    assertions.Template.from_stack(stack)
