
import copy
import sys
import httplib2
import os
from apiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials
from oauth2client.client import AccessTokenRefreshError

# To run: rollout_update package_name json_credentials_path track force_user_fraction
def main():
  PACKAGE_NAME = sys.argv[1]
  TRACK = sys.argv[3]
  FORCE_USER_FRACTION = float(sys.argv[4] or "0")
  STEPS = sys.argv[5].split(",")
  for i, step in enumerate(STEPS):
    STEPS[i] = float(step) / 100.0
  STEPS.append(1.0)
  MAX_CRASH_RATE = float(sys.argv[6] or "0.1")
  
  # outputs
  ROLLOUT_RESULT = "none"
  ROLLOUT_PERCENT = ""
  CRASH_RATE = ""
  VERSION_NAME = ""
  VERSION_CODE = ""

  credentials = ServiceAccountCredentials.from_json_keyfile_name(
    sys.argv[2],
    scopes=['https://www.googleapis.com/auth/androidpublisher','https://www.googleapis.com/auth/playdeveloperreporting'])

  http = httplib2.Http()
  http = credentials.authorize(http)

  service = build('androidpublisher', 'v3', http=http)
  crash_service = build("playdeveloperreporting", "v1beta1", http=http, cache_discovery=False)
  
  try:
    edit_request = service.edits().insert(body={}, packageName=PACKAGE_NAME)
    result = edit_request.execute()
    edit_id = result['id']

    track_result = service.edits().tracks().get(editId=edit_id, packageName=PACKAGE_NAME, track=TRACK).execute()
    old_result = copy.deepcopy(track_result)

    print("Current status: ", track_result)
    for release in track_result['releases']:
        version_filter = "versionCode=" + release['versionCodes'][0]
        VERSION_CODE = release['versionCodes'][0]
        VERSION_NAME = release['name']
  
        crash_info = crash_service.vitals().crashrate().get(name="apps/" + PACKAGE_NAME + "/crashRateMetricSet").execute()
        
        print("Crash api info: ",crash_info)
        
        endTime = {}
        
        for freshness in crash_info['freshnessInfo']['freshnesses']:
            if freshness['aggregationPeriod'] == "DAILY":
                endTime = freshness['latestEndTime']
                
        startTime = copy.deepcopy(endTime)
        startTime['day'] = startTime['day'] - 1
          
        body = {
            "dimensions": ["versionCode"],
            "filter": version_filter,
            "metrics": ["userPerceivedCrashRate7dUserWeighted"],
            "timelineSpec": {"aggregationPeriod": "DAILY",
                "endTime": endTime,
                "startTime": startTime
            }}
  
        crash_rate_data = crash_service.vitals().crashrate().query(name="apps/" + PACKAGE_NAME + "/crashRateMetricSet", body=body).execute()
        print("Crash rate info: ", crash_rate_data)
        
        crash_rate = 0
        
        if 'rows' in crash_rate_data and len(crash_rate_data['rows'] > 0):
            metrics = crash_rate_data['rows'][0]['metrics']
            for metric in metrics:
                metric_key = metric['metric']
                if metric_key == 'userPerceivedCrashRate7dUserWeighted':
                    crash_rate = float(metric['decimalValue']['value'])
        
        CRASH_RATE = str(crash_rate)
        
        if 'userFraction' in release:
            rolloutPercentage = release['userFraction']
            if crash_rate < MAX_CRASH_RATE:
                if FORCE_USER_FRACTION > 0:
                    rolloutPercentage = FORCE_USER_FRACTION
                    print('Forcing rollout to', rolloutPercentage)
                else:      
                    if rolloutPercentage <= 0.0001:
                        print('Release not rolled out yet')
                        continue  
                    elif rolloutPercentage == 1.0:
                        print('Release already fully rolled out')
                        continue
                    else:
                        for step in STEPS:
                            if rolloutPercentage < step:
                                rolloutPercentage = step
                                break 
                if rolloutPercentage < 1:
                    print('Updating rollout to', rolloutPercentage)
                    release['userFraction'] = rolloutPercentage
                else:
                    print('Marking rollout completed', rolloutPercentage)
                    del release['userFraction']
                    release['status'] = 'completed'
                ROLLOUT_RESULT = 'updated'
            else:
                ROLLOUT_RESULT = 'critical_crash'
            
            ROLLOUT_PERCENT = str(rolloutPercentage)
            break
    

    if old_result != track_result:
        completed_releases = list(filter(lambda release: release['status'] == "completed", track_result['releases']))
        if len(completed_releases) == 2:
            track_result['releases'].remove(completed_releases[1])

        print("Updating status: ", track_result)
        service.edits().tracks().update(
                    editId=edit_id,
                    track=TRACK,
                    packageName=PACKAGE_NAME,
                    body=track_result).execute()
        commit_request = service.edits().commit(editId=edit_id, packageName=PACKAGE_NAME).execute()
        print('✅ Edit ', commit_request['id'], ' has been committed')    
    else:
        if crash_rate >= MAX_CRASH_RATE:
            print("⚠️ Too much crash !!!", crash_rate)
        else:
            print('✅ No rollout update needed')
    
    print('> ROLLOUT_RESULT=' + ROLLOUT_RESULT)
    print('> ROLLOUT_PERCENT=' + str(ROLLOUT_PERCENT))
    print('> CRASH_RATE=' + str(CRASH_RATE))
    print('> VERSION_NAME=' + str(VERSION_NAME))  
    print('> VERSION_CODE=' + str(VERSION_CODE))
    os.system('envman add --key ROLLOUT_RESULT --value "${' + ROLLOUT_RESULT + '}"')
    os.system('envman add --key ROLLOUT_PERCENT --value "${' + ROLLOUT_PERCENT + '}"')
    os.system('envman add --key CRASH_RATE --value "${' + CRASH_RATE + '}"')
    os.system('envman add --key VERSION_NAME --value "${' + VERSION_NAME + '}"')
    os.system('envman add --key VERSION_CODE --value "${' + VERSION_CODE + '}"')

  except AccessTokenRefreshError:
      raise SystemExit('The credentials have been revoked or expired, please re-run the application to re-authorize')

if __name__ == '__main__':
  main()
