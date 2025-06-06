from aws_cdk import App
from cdk.HumanToneStack import HumanToneStack  # Correct import


app = App()

HumanToneStack(app, "HumanToneStack")

app.synth()
