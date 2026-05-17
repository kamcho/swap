from django.contrib import sitemaps
from django.urls import reverse

class StaticViewSitemap(sitemaps.Sitemap):
    priority = 0.5
    changefreq = 'daily'

    def items(self):
        # Add names of views you want in the sitemap
        return ['core:home', 'accounts:find_swaps', 'core:privacy_policy']

    def location(self, item):
        return reverse(item)

class HomeSitemap(sitemaps.Sitemap):
    priority = 1.0
    changefreq = 'daily'

    def items(self):
        return ['core:home']

    def location(self, item):
        return reverse(item)
