# SWPanel

Design an ESPHome LVGL touch panel by dragging elements around, then paste the YAML into
ESPHome Builder.

## Using it

1. Open **SWPanel** from the sidebar. Only Home Assistant administrators can see it.
2. Choose your display, lay out your page and pick your entities. Entity lookup works
   straight away, with no token to set up.
3. Select **Get YAML**, then paste the result into a new device in ESPHome Builder.

The preview shows your entities' real states, refreshed every 3 seconds. Clicking a tile selects
it rather than switching it. Tick **Show tiles on** to style the on colours whatever the real
state is.

Designs and uploaded images are stored in the app's data folder and included in Home
Assistant backups.

## Image address

ESPHome downloads uploaded images when it compiles, so it has to be able to reach this app.
The YAML uses the app's internal address, which works when ESPHome Builder runs as an app on
this same Home Assistant.

If a compile can't download an image:

1. In this app's **Configuration** tab, under **Network**, set a port such as `8095`.
2. Set **Image address** to `http://<your Home Assistant IP>:8095`.
3. Restart the app, then select **Get YAML** again.

Only images are served on that port. The designer itself stays behind your Home Assistant login.

## Permissions

The app reads your entity list through Home Assistant's API, and the Supervisor gives it
administrator-level access to do so. The app only ever reads `/api/states`, and it never sends
your data anywhere else.
