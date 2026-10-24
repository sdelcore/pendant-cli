"""Response handling shared by all client backends (D-Bus, Bleak)."""

from . import protocol as _protocol


class ResponseHandlerMixin:
    """Prints and accumulates parsed pendant responses.

    Backends must provide: ``protocol``, ``private_key``, ``opus_data``, ``pcm_data``,
    ``encrypted_data``, ``page_count``, ``responses``, ``page_timestamps``,
    ``on_response``, ``_status_printed`` and ``_info_printed``.
    """

    def _handle_response(self, response: dict):
        """Process parsed response."""
        rtype = response.get("type")
        self.responses.append(rtype)

        if rtype == "device_info":
            if not self._info_printed:
                print(f"\n  Device: {response.get('device_name', 'Unknown')}")
                print(f"  Firmware: {response.get('firmware_version', '?')}")
                print(f"  Hardware: {response.get('hardware_version', '?')}")
                print(f"  Serial: {response.get('serial_number', '?')}")
                self._info_printed = True

        elif rtype == "device_status":
            if not self._status_printed:
                is_recording = response.get('is_recording', False)
                print(f"\n  Recording: {is_recording}")
                print(f"  Storage: {response.get('storage_used_percent', 0)}%")
                print(f"  (LED is authoritative: solid white = recording)")
                self._status_printed = True

        elif rtype == "battery_status":
            print(f"\n  Battery: {response.get('level', 0)}%")
            if response.get('charging'):
                print(f"  Charging: yes")

        elif rtype == "set_current_time_response":
            print(f"\n  Time synced: {response.get('success', False)}")

        elif rtype == "storage_buffer":
            self.page_count += 1
            flash_page = response.get("flash_page", b"")
            if flash_page:
                if _protocol.DEBUG_MODE:
                    print(f"\n  Page {self.page_count}: flash_page={len(flash_page)}B")
                opus, pcm, encrypted, _, page_info = self.protocol.extract_audio_from_flash_page(flash_page, self.private_key)
                # Track audio offset for this page
                page_info["audio_offset_bytes"] = len(self.opus_data)
                self.page_timestamps.append(page_info)
                self.opus_data.extend(opus)
                self.pcm_data.extend(pcm)
                self.encrypted_data.extend(encrypted)
            if not _protocol.DEBUG_MODE:
                enc_str = f" enc={len(self.encrypted_data)}B" if self.encrypted_data else ""
                print(f"\r  Page {self.page_count}: opus={len(self.opus_data)}B pcm={len(self.pcm_data)}B{enc_str}", end="", flush=True)

        elif rtype and rtype != "parse_error":
            print(f"\n  Response: {rtype}")

        if self.on_response:
            self.on_response(response)
