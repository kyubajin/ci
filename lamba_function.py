import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader
import uuid
import io
import boto3

from base64 import b64decode
from os import path
from urllib.parse import parse_qs

from datetime import datetime
import numpy as np

# Initialize SOLUTION & SD_OPTIM empty
SOLUTION = int()
SD_OPTIM = int()

# S3 Bucket parameters
BUCKET_NAME = 'kyubajin'
SERVICE_NAME = 's3'
REGION_NAME = 'eu-north-1'
DOMAIN_NAME = 'amazonaws.com'
BUCKET_URL = f'https://{BUCKET_NAME}.{SERVICE_NAME}.{REGION_NAME}.{DOMAIN_NAME}'

# guessing game parameters
CURVE_RANGE = 0.126 # marks the 90% accuracy
LINE_SPACE = 1000
MIN_PLAYERS = 10 # minimum number of players for a valid graph
Z_SCORE = 3 # standard deviations from the mean value

# plot line colors
GUESS_COLOR = 'red'
MEAN_COLOR = 'blue'
SOLUTION_COLOR = 'green'


print('Loading function!!!')

def lambda_handler(event, context):
    # create the jinja2 Environment
    env = Environment(
            # get the directory path of this file, and add 'templates'. That's where to find them.
            loader=FileSystemLoader(path.join(path.dirname(__file__), 'templates'),
            encoding='utf8')
        )
    
    try:
        http_method = event.get('requestContext').get('httpMethod')
    except Exception as e:
        template = env.get_template('error.html')
        return response(template.render(error=e))

    # if this is a GET then send the page with the form
    if http_method == 'GET':
        template = env.get_template('index.html')
        # the index.html template doesn't require any variables, so we can just render it.
        return response(template.render())

    # if this is a POST, then get the guess values, process them and return a formatted page of results
    elif http_method == 'POST':
        # list of all the plots we're going to create
        plot_list = []

        # guess_list ends up being the list of integers we want it to be
        try:
            params = parse_qs(b64decode(event.get('body')).decode('utf-8'))
            print('params', params)
            guesses_string = params.get('guesses')[0]
            print('SOLUTION VALUE', params.get('solutionValue')[0])
            SOLUTION = int(params.get('solutionValue')[0])
            print('guesses_string', guesses_string)
            guess_list = list(map(int, guesses_string.split()))
            guess_list = np.array(guess_list)
            assert len(guess_list) >= MIN_PLAYERS
        except AssertionError as e:
            print(f"Minimum number of players is {MIN_PLAYERS}, you entered only {len(guess_list)}")
            template = env.get_template('error.html')
            return response(template.render(error=e))
        except Exception as e:
            print(f"{e}")
            template = env.get_template('error.html')
            return response(template.render(error=e))

        # Group statistics
        SD_OPTIM = int(SOLUTION*0.3) # curve amplitude
        minrange = round(SOLUTION - CURVE_RANGE * SD_OPTIM)
        maxrange = round(SOLUTION + CURVE_RANGE * SD_OPTIM)

        mean_guess = np.mean(guess_list).astype(int)
        sorted_guess = np.sort(guess_list)

        low_acc = np.sum((guess_list < minrange) | (guess_list > maxrange))
        high_acc = len(guess_list) - low_acc
        sum_match = np.sum(guess_list == SOLUTION)
        group_over_ind = round(np.sum(np.abs(SOLUTION - guess_list) > np.abs(SOLUTION - mean_guess)) / len(guess_list) * 100)

        # fig 1. Histogram of Individual Guesses
        # Define the cuts
        cuts = np.arange((min(guess_list) // 10) * 10, (max(guess_list) // 10) * 10 + 10, 10)
        # Create the histogram
        plt.clf()
        plt.hist(guess_list, bins=cuts, color='blue', alpha=0.7)
        plt.xlabel('Guesses')
        plt.ylabel('Frequency')
        plt.yticks(np.arange(0, plt.hist(guess_list, bins=cuts)[0].max() + 1, 1))  # Set y-axis label intervals to 1
        #plot_list.append({ 'url': save_to_s3(plt), 'caption': 'Fig. 1: Histogram of Individual Guesses', 'description': f'Your individual responses have been: <br> {guess_list} <br> Your average (group mean) is: {mean_guess}' })
        sorted_guess_list = sorted(guess_list)
        plot_list.append({ 
            'url': save_to_s3(plt), 
            'caption': 'Fig. 1: Histogram of Individual Guesses', 
            'description': f'Your individual responses have been: <br> {", ".join(map(str, sorted_guess_list))} <br> Your average (group mean) is: {mean_guess}' 
        })



        # Outlier graphic control Function
        # Calculate IQR
        iqr_guess = np.percentile(guess_list, 75) - np.percentile(guess_list, 25)
        # Calculate quantiles
        quantile1 = np.percentile(guess_list, 25)
        quantile3 = np.percentile(guess_list, 75)
        # Calculate low and high outliers
        low_outlier = int(quantile1 - 1.5 * iqr_guess)
        high_outlier = int(quantile3 + 1.5 * iqr_guess)
        # Filter guess_list
        guess_list2 = guess_list[(guess_list > low_outlier) & (guess_list < high_outlier)]

        # fig 2. Normal Distribution
        plt.clf()
        plot_curve(SOLUTION, SD_OPTIM)
        plt.axvline(x=SOLUTION, color=SOLUTION_COLOR, linewidth=2)
        plt.yticks([])  # Remove y-axis numbers
        plt.xticks([])  # Remove x-axis numbers
        plot_list.append({ 'url':save_to_s3(plt), 'caption':'Fig. 2: Normal Distribution', 'description': 'The central value of this curve, <br> represented with a green line, <br> marks the actual number of sweets in the jar.' })

        # fig 3. Number of Sweets with 90% Quality Score
        plt.clf()
        plot_curve(SOLUTION, SD_OPTIM)
        plt.axvline(x=SOLUTION, color=SOLUTION_COLOR, linewidth=2)
        plt.axvline(x=minrange, color=SOLUTION_COLOR)
        plt.axvline(x=maxrange, color=SOLUTION_COLOR)
        plt.yticks([])  # Remove y-axis numbers
        plt.xticks([])  # Remove x-axis numbers
        plot_list.append({ 'url':save_to_s3(plt), 'caption':'Fig. 3: Number of Sweets & Quality Score', 'description': 'The new green lines to the left and right of the central value <br> represent an accuracy range greater than 90%. <br>' })

        # fig 4. Individual Guesses
        plt.clf()
        plot_curve(SOLUTION, SD_OPTIM)
        plt.axvline(x=SOLUTION, color=SOLUTION_COLOR, linewidth=2)
        plt.axvline(x=minrange, color=SOLUTION_COLOR)
        plt.axvline(x=maxrange, color=SOLUTION_COLOR)
        for g in guess_list2:
            plt.axvline(x=g, color=GUESS_COLOR, linewidth=0.5)
        plt.yticks([])  # Remove y-axis numbers
        plot_list.append({ 'url':save_to_s3(plt), 'caption':'Fig. 4: Individual Guesses', 'description': f'A total of {low_acc} individual responses are under 90% accuracy. <br> {high_acc} individual responses have crossed 90% accuracy. <br> There are {sum_match} exact matches.' })

        # fig 5. Group result
        plt.clf()
        plot_curve(SOLUTION, SD_OPTIM)
        plt.axvline(x=SOLUTION, color=SOLUTION_COLOR, linewidth=2)
        plt.axvline(x=minrange, color=SOLUTION_COLOR)
        plt.axvline(x=maxrange, color=SOLUTION_COLOR)
        plt.axvline(x=mean_guess, color=MEAN_COLOR)
        plt.yticks([])  # Remove y-axis numbers
        plot_list.append({ 'url':save_to_s3(plt), 'caption':'Fig. 5: Group result', 'description': f'As a group, you estimated {mean_guess} sweets. <br> The actual number of sweets is {SOLUTION} <br> The 90% quality range was located between {minrange} and {maxrange}.' })

        # fig 6. Mixed result
        plt.clf()
        plot_curve(SOLUTION, SD_OPTIM)
        plt.axvline(x=SOLUTION, color=SOLUTION_COLOR, linewidth=2)
        plt.axvline(x=minrange, color=SOLUTION_COLOR)
        plt.axvline(x=maxrange, color=SOLUTION_COLOR)
        plt.axvline(x=mean_guess, color=MEAN_COLOR)
        for g in guess_list2:
            plt.axvline(x=g, color=GUESS_COLOR, linewidth=0.5)
        plt.yticks([])  # Remove y-axis numbers
        plot_list.append({ 'url':save_to_s3(plt), 'caption':'Fig. 6: Mixed result', 'description': f'You, as a group, have beaten {group_over_ind}% of individuals. <br> <br> ' })

        template_ctx = {
            'plot_list': plot_list,
            'low_acc': low_acc,
            'high_acc': high_acc,
            'sum_match': sum_match,
            'group_over_ind': group_over_ind,
            'sorted_guess': sorted_guess,
            'mean_guess': mean_guess,
            'minrange': minrange,
            'maxrange': maxrange,
            'SOLUTION': SOLUTION,
        }
        
        print('template_ctx:', template_ctx,)

        # get the template...
        template = env.get_template('results.html')

        # render the template with the variables in context
        # the **context syntax changes the dict into named function parameters
        return response(template.render(**template_ctx))

    else:
        print("What if it's neither a GET nor a POST? This is an error and should be handled gracefully here!")
        return response('<html><head></head><body><h1>Bad request</h1></body></html>', code=403)


def response(myhtml, code=200):
    return {
        "statusCode": code,
        "body": myhtml,
        "headers": {
            "Content-Type": "text/html",
        }
    }

# draw the curve
def plot_curve(SOLUTION, SD_OPTIM):
    x = np.linspace(SOLUTION - Z_SCORE * SD_OPTIM, SOLUTION + Z_SCORE * SD_OPTIM, LINE_SPACE)
    plt.plot(x, 1 / (SD_OPTIM * np.sqrt(2 * np.pi)) * np.exp(- (x - SOLUTION) ** 2 / (2 * SD_OPTIM ** 2)), 'b-')

def save_to_s3(plot):
    fname = '{:%Y%m%d%H%M%S}-{}.png'.format(datetime.now(), str(uuid.uuid4().hex))
    png_data = io.BytesIO()
    plot.savefig(png_data)
    png_data.seek(0)

    # Upload the data to S3
    s3 = boto3.client('s3', region_name='eu-north-1')
    s3.put_object(Bucket=BUCKET_NAME, Key=fname, Body=png_data)

    # Returns URL
    url = f"{ BUCKET_URL }/{ fname }"
    print('url', url)

    return url
    
