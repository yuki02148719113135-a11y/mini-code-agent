#!/usr/bin/env python3
"""
ミニ保守解析エージェント用ネットワーク（CDK / Python）

方針:
  - インターネットへの出口なし（NAT・IGWなし、隔離サブネットのみ）
  - Bedrock と CloudWatch Logs だけ VPC エンドポイント経由で使う
  - エージェントのSGは「VPC内の443番」にしか出られない（二重の守り）
  - 使わない期間は `cdk destroy` で丸ごと消す（エンドポイントの時間課金を止める）
"""
import os

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class MiniAgentNetworkStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. VPC: 隔離サブネットのみ。NATゲートウェイ0台＝外へ出る経路そのものが無い
        vpc = ec2.Vpc(
            self, "Vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.50.0.0/16"),
            max_azs=2,  # AZを増やすとエンドポイント料金も比例して増える
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                )
            ],
        )

        # 2. セキュリティグループ
        #    エージェント側: 外向きはVPC内の443番だけ許可（＝エンドポイントにしか行けない）
        agent_sg = ec2.SecurityGroup(
            self, "AgentSg",
            vpc=vpc,
            allow_all_outbound=False,
            description="Agent runtime: egress to VPC endpoints only",
        )
        agent_sg.add_egress_rule(
            ec2.Peer.ipv4(vpc.vpc_cidr_block), ec2.Port.tcp(443),
            "HTTPS to VPC endpoints only",
        )

        #    エンドポイント側: エージェントSGからの443番だけ受け付ける
        endpoint_sg = ec2.SecurityGroup(
            self, "EndpointSg",
            vpc=vpc,
            allow_all_outbound=False,
            description="Interface endpoints: ingress from agent only",
        )
        endpoint_sg.add_ingress_rule(agent_sg, ec2.Port.tcp(443), "From agent")

        # 3. VPCエンドポイント（必要最小限。デプロイ時に足りないと言われたら追加する）
        endpoints = {
            "BedrockRuntime": ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME,
            "Logs": ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
        }
        for name, service in endpoints.items():
            vpc.add_interface_endpoint(
                name,
                service=service,
                security_groups=[endpoint_sg],
                private_dns_enabled=True,
            )

        # 3b. S3 ゲートウェイエンドポイント（無料）
        #     AgentCore Runtime は起動時にコード一式を S3 から取得するため、NATなしのVPCでは必須
        vpc.add_gateway_endpoint(
            "S3",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)],
        )
        #     エージェントSGの出口に「S3 の宛先リスト（プレフィックスリスト）」だけを追加する
        s3_pl = ec2.PrefixList.from_lookup(
            self, "S3PrefixList", prefix_list_name=f"com.amazonaws.{self.region}.s3"
        )
        agent_sg.add_egress_rule(
            ec2.Peer.prefix_list(s3_pl.prefix_list_id), ec2.Port.tcp(443),
            "HTTPS to S3 via gateway endpoint only",
        )

        # 4. AgentCore Runtime の VPC 設定に渡す値を出力
        cdk.CfnOutput(
            self, "SubnetIds",
            value=",".join(s.subnet_id for s in vpc.isolated_subnets),
        )
        cdk.CfnOutput(self, "AgentSecurityGroupId", value=agent_sg.security_group_id)


app = cdk.App()
MiniAgentNetworkStack(
    app, "MiniAgentNetwork",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),  # プレフィックスリストの検索に必要
        region="ap-northeast-1",
    ),
)
cdk.Tags.of(app).add("Project", "mini-agent")
app.synth()
