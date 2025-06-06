
from aws_cdk import App
from cdk import HumanToneStack


app = App()

HumanToneStack(app, "HumanToneStack")

app.synth()
