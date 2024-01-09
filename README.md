# replace_ucode
Hacky script to replace Intel microcode in a UEFI ROM image.

Looks for the UUID 197DB236-F856-4924-90F8-CDF12FB875F3 in a given rom image file.
For each instance of that UUID, it tries to parse a UEFI FFS header at that spot, and, if that succeeds, replaces the FFS body with a given microcode file.

I've only used it to play around with old microcode, but it might work for adding support for a newer CPU to a motherboard that doesn't officially support it.
Use at your own risk.
