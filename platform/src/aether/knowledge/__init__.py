"""What one agent remembers about one business.

Isolated per tenant by the same row-level security as everything else, and
tested harder than anything else, because this is the only tenant table that
holds sentences rather than numbers.
"""
