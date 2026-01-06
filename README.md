所有的categories: AirConditioner, Blind, Charger, Fan, Hub, Light, NetworkAudio, Others, Switch, Television, Washer, SmartPlug

总结方案1的详细步骤，遵守claude.md中的设计和思考原则，用户设备获取通过get：https://api.samsungiotcloud.cn/v1/devices?locationId=f4b3af92-5826-416e-8e28-8b1c252912f1。数据返回格式放到readme中了.

"items": [
		{
			"deviceId": "f3057397-d758-4914-b6c5-5906321a6537",
			"name": "顶灯",
			"label": "顶灯",
			"manufacturerName": "SmartThings",
			"presentationId": "SmartThings-smartthings-Opple_Lamp_KR",
			"locationId": "b78ee6da-7a9f-427c-ac8c-99e318139410",
			"ownerId": "f90544c2-d6d1-b584-50c0-6533abb061dd",
			"roomId": "cf5a384e-77e0-47ec-b201-3b73d1655853",
			"components": [
				{
					"id": "main",
					"label": "main",
					"capabilities": [
						{
							"id": "ocf",
							"version": 1
						},
						{
							"id": "execute",
							"version": 1
						},
						{
							"id": "refresh",
							"version": 1
						},
						{
							"id": "switch",
							"version": 1
						},
						{
							"id": "switchLevel",
							"version": 1
						},
						{
							"id": "activityLightingMode",
							"version": 1
						},
						{
							"id": "colorTemperature",
							"version": 1
						}
					],
					"categories": [
						{
							"name": "Light",
							"categoryType": "manufacturer"
						}
					],
					"optional": false
				}
			],
			"createTime": "2025-05-16T07:08:44.177Z",
			"profile": {
				"id": "a38eafbd-1ebb-3e1a-861e-122774e78ef3"
			},
			"virtual": {
				"name": "顶灯",
				"executingLocally": false
			},
			"type": "VIRTUAL",
			"restrictionTier": 0,
			"allowed": [],
			"executionContext": "CLOUD",
			"relationships": []
		}
]