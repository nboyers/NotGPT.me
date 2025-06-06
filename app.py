#!/usr/bin/env python3
# from aws_cdk import App  # Import specific class for App creation
# from cdk.HumanToneStack import HumanToneStack  # Import HumanToneStack from cdk package

app = App()

HumanToneStack(app, "HumanToneStack")

app.synth()
