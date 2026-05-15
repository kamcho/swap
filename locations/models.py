from django.db import models

class County(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Counties"

class SubCounty(models.Model):
    county = models.ForeignKey(County, on_delete=models.CASCADE, related_name='subcounties')
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} ({self.county.name})"
    
    class Meta:
        verbose_name_plural = "Sub-Counties"
        unique_together = ('county', 'name')

class Ward(models.Model):
    subcounty = models.ForeignKey(SubCounty, on_delete=models.CASCADE, related_name='wards')
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} ({self.subcounty.name})"
    
    class Meta:
        unique_together = ('subcounty', 'name')
