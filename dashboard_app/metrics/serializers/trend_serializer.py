from rest_framework import serializers


class TrendPointSerializer(
    serializers.Serializer
):
    date = serializers.DateField()
    value = serializers.FloatField()
