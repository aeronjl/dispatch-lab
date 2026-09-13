----------------------------- MODULE Reactor -----------------------------
EXTENDS Integers, TLC
CONSTANT MinimumRun
VARIABLES mode, remaining, prevRemaining, prevRunning, requested,
          beginningSafe, endingSafe, resources, failure, started
vars == <<mode, remaining, prevRemaining, prevRunning, requested,
          beginningSafe, endingSafe, resources, failure, started>>
Init == /\ mode = "off" /\ remaining = 0 /\ prevRemaining = 0
        /\ prevRunning = FALSE /\ requested = FALSE /\ started = FALSE
        /\ beginningSafe = FALSE /\ endingSafe = FALSE
        /\ resources = FALSE /\ failure = FALSE
Next == \E want, heat, hot, b, e, supply, failed \in BOOLEAN:
    LET active == (want \/ remaining > 0) /\ b /\ e /\ supply /\ ~failed
        start == active /\ mode # "running"
        trip == ~active /\ (remaining > 0 \/ want)
    IN /\ mode' = IF trip THEN "forced-trip" ELSE IF active THEN "running"
                  ELSE IF heat THEN "warming" ELSE IF hot THEN "cooling" ELSE "off"
       /\ remaining' = IF ~active THEN 0 ELSE IF start THEN MinimumRun - 1
                        ELSE IF remaining > 0 THEN remaining - 1 ELSE 0
       /\ prevRemaining' = remaining /\ prevRunning' = (mode = "running")
       /\ requested' = want /\ beginningSafe' = b /\ endingSafe' = e
       /\ resources' = supply /\ failure' = failed /\ started' = start
TypeOK == /\ mode \in {"off", "warming", "running", "cooling", "forced-trip"}
          /\ remaining \in 0..(MinimumRun - 1)
SafeProduction == mode = "running" => beginningSafe /\ endingSafe /\ resources /\ ~failure
Commitment == prevRemaining > 0 /\ beginningSafe /\ endingSafe /\ resources /\ ~failure => mode = "running"
ExplicitTrip == (prevRemaining > 0 \/ requested) /\ mode # "running" => mode = "forced-trip"
StartCount == started => remaining = MinimumRun - 1 /\ ~prevRunning
StopCount == mode # "running" => remaining = 0
ContinueCount == mode = "running" /\ prevRunning => remaining = (IF prevRemaining > 0 THEN prevRemaining - 1 ELSE 0)
Spec == Init /\ [][Next]_vars
=============================================================================
