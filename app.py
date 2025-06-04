#!/usr/bin/env python3
import aws_cdk as cdk

from cdk.HumanToneStack import HumanToneStack


app = cdk.App()

HumanToneStack(app, "HumanToneStack")

app.synth()
