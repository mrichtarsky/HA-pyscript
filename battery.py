from datetime import datetime, time


feedin = []
previous_g = None

@time_trigger('period(0:00, 10 sec)')
def battery_control():
    '''
    - Battery is charged first, then car
    - Battery is plugged into Phase 3
    - Optimized for summer, recheck in winter
    - L1 is not available and must be calculated from the other values
    '''
    global previous_g
    CHARGE_MAX_FEEDIN_PERCENTAGE = 0.98
    MAX_DISCHARGE = 2000.0
    MAX_CHARGE = 1000.0
    MIN_CHARGING_POWER = 1100
    now = datetime.now()

    battery_enabled = state.get('input_boolean.custom_enable_disable_battery') == 'on'
    discharge = float(state.get('sensor.msa_280024340863_power_from_to_battery'))
    g = float(state.get('sensor.evcc_grid_power'))
    # When g did not change, do not do anything. The inverter is slower to update the
    # values than this automation, and without this check it can happen that we
    # compensate again because the previous compensation is not reflected yet.
    if g == previous_g:
        return
    previous_g = g
    g += discharge
    # Positive is feedin, so negate
    l2 = -float(state.get('sensor.solax_measured_power_l2'))
    l3 = -float(state.get('sensor.solax_measured_power_l3')) + discharge
    soc = float(state.get('sensor.msa_280024340863_state_of_charge'))
    wallbox = 1000 * float(state.get('sensor.evcc_garage_charge_power'))
    l1 = g - l2 - l3
    feedin.append(g)
    if len(feedin) > 6*3:  # 3 minutes
        feedin.pop(0)
    discharge_new = 0.0
    evcc_mode = select.evcc_garage_mode
    # In winter, we do not have enough power for car and battery. Rather charge the
    # car to save battery cycles.
    if now.month >= 9 and now.month <= 3:
        consume_from_wallbox = False
    else:
        consume_from_wallbox = (
            evcc_mode == 'Solar' and wallbox > 10
            or evcc_mode == 'Min+Solar' and wallbox > MIN_CHARGING_POWER
        )
    if not battery_enabled:
        mode = 'disabled'
        discharge_new = discharge
    elif g > 0 and soc > 5 and wallbox < 10:
        mode = 'discharge'
        discharge_new = min(g, MAX_DISCHARGE)
        # At night, we empty the whole battery. Since power usage fluctuates, we
        # sometimes feed in too much. Always feed in 100W less during that time to avoid
        # wasting power.
        if now.hour >= 17 or now.hour < 9:
            discharge_new -= 100
    elif soc < 100.0 and (all([x < -20.0 for x in feedin]) or consume_from_wallbox):
        mode = 'charge'
        if consume_from_wallbox:
            # Charge battery before car: Use the power the wallbox consumes so evcc switches it off
            if evcc_mode == 'Solar':
                from_wallbox = wallbox
            else:
                from_wallbox = wallbox - MIN_CHARGING_POWER
        discharge_new = -min(CHARGE_MAX_FEEDIN_PERCENTAGE * (abs(g) + from_wallbox), MAX_CHARGE)
    else:
        mode = 'idle'
    if discharge == discharge_new:
        discharge_new += 0.1
    log.error(f'usage={g-discharge}, grid={g}, l1={l1}, l2={l2}, l3={l3}, l1+l2+l3={l1+l2+l3}, wallbox={wallbox}, soc={soc}, discharge={discharge}, mode={mode}, discharge_new={discharge_new}')
    mqtt.publish(topic='homeassistant/number/MSA-280024340863/power_ctrl/set', payload=discharge_new)
    state.set('number.msa_280024340863', discharge_new)
