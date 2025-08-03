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
    battery_enabled = state.get('input_boolean.custom_enable_disable_battery') == 'on'
    discharge = float(state.get('sensor.msa_280024340863_power_from_to_battery'))
    g = float(state.get('sensor.evcc_grid_power'))
    # When g did not change, do not do anything. The inverter is slower to update the
    # values than this automation, and without this check it can happen that we
    # compensate again because the previous compensation is not reflected yet.
    if g == previous_g:
        return
    previous_g = None
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
    if not battery_enabled:
        mode = 'disabled'
    elif g > 0 and soc > 5 and wallbox < 10:
        mode = 'discharge'
        discharge_new = min(g, MAX_DISCHARGE)
    elif soc < 100.0 and (all([x < -20.0 for x in feedin]) or wallbox > 10):
        mode = 'charge'
        # Charge battery before car: Use the power the wallbox consumes so evcc switches it off
        discharge_new = -min(CHARGE_MAX_FEEDIN_PERCENTAGE * (abs(g) + wallbox), MAX_CHARGE)
    else:
        mode = 'idle'
    if discharge == discharge_new:
        discharge_new += 0.1
    log.error(f'grid={g}, l1={l1}, l2={l2}, l3={l3}, l1+l2+l3={l1+l2+l3}, wallbox={wallbox}, soc={soc}, discharge={discharge}, mode={mode}, discharge_new={discharge_new}')
    mqtt.publish(topic='homeassistant/number/MSA-280024340863/power_ctrl/set', payload=discharge_new)
    state.set('number.msa_280024340863', discharge_new)
