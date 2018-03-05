# fwdform2

A simple server for forwarding web forms to email addresses.

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

Inspired by [fwdform](https://github.com/samdobson/fwdform).

## Use cases

* You want to forward a simple contact form to an email address.
* You have a (S3) static site and don't want to run a server.
* You want to forward arbitrary form fields formatted as human-readable email.
* You want to automatically respond (with a template) to users when they submit a form.

## Prerequisites

* A free [Heroku](https://www.heroku.com) account.
* A free [Mailgun](https://www.mailgun.com) account.
* The [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli).

In order to take advantage of your free monthly Mailgun email quota, after signing up, please follow the instructions to setup and verify your Mailgun domain name.

**Note:** Mailgun requires you to select the Concept plan and provide credit card details to move your domain out of the sandbox (even though you still get 10,000 free emails per month). However, for basic usage, you can leave your domain in the sandbox and manually enter each email recipients as Mailgun [Authorized Recipients](https://app.mailgun.com/app/account/authorized).

## Manually deploy to Heroku

If you don't want to deploy manually, press the "Deploy to Heroku" button at the top of the page.

1. Clone fwdform2:

    ```bash
    git clone https://github.com/glassechidna/fwdform2.git
    ```

2. Create a Heroku app, add a PostgreSQL database and configure your Mailgun details:

    ```bash
    heroku create
    heroku addons:add heroku-postgresql:hobby-dev
    heroku config:set MAILGUN_DOMAIN=<MAILGUN_DOMAIN> \
                      MAILGUN_API_KEY=<KEY> \
                      REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
    ```

    Setting `REQUESTS_CA_BUNDLE` as `/etc/ssl/certs/ca-certificates.crt` ensures that the host's SSL certificate authorities are utilised rather than the (potentially dated) CAs packaged with Python. In the past this has proven to be be necessary to communicate with Mailgun, so this is a suggested setting.

3. Deploy fwdform2 to your Heroku app:

    ```bash
    git push heroku master
    ```

4. Run the setup script and ensure one dyno is running:

    ```bash
    heroku run ./setup.py
    heroku ps:scale web=1
    ```

    `setup.py` will perform one-time app setup e.g. creating the database.

## Usage

### Your Heroku Web URL

General usage of fwdform2 will require you to know your Heroku Web URL (`WEB_URL`).

Your Heroku Web URL was printed when your first setup your Heroku app, however you can retrieve it again by entering:

```bash
heroku info
```

### Registration API

A simple API is provided to register email receivers. However, for security reasons it is disabled by default.

You can enable it as follows:

```bash
heroku config:set REGISTRATION_ENABLED=yes \
                  REGISTRATION_PASSWORD=<SOME_PASSWORD>
```

Although it's password protected, it is suggested that you disable the registration API when you've finished using it.

```bash
heroku config:unset REGISTRATION_ENABLED REGISTRATION_PASSWORD
```

**Note:** Don't forget to either move your Mailgun domain out of the sandbox mode, or alternatively add each user as an [Authorized Recipient](https://app.mailgun.com/app/account/authorized).

### Register a user

**Endpoint:** `/user/<register>` (HTTP POST)

Parameters:

 * email

Returns:

 * private_token
 * public_token

#### Registering a user from command line

One of the simplest ways to register a user is to call the registration API from command line as follows:

```bash
curl --data "email=<your_email>&password=<your_password>" <WEB_URL>/register
```

This will return information in the form:

```
Public token: <public_token>, Private token: <private_token>
```

Write down or otherwise save these two pieces of information.

Keep the private token to yourself, it's effectively your password, associated with `<your_email>`. You will need this token to take advantage of some advanced features of fwdform2.

You will need the public token for setting up forms on your website, this is not secret.

### Delete a user

**Endpoint:** `/user/<public_token>` (HTTP DELETE)

Parameters:

 * token

Token is the user's `private_token`.

#### Deleting a user from command line

```bash
curl -X DELETE --data "token=<private_token>" <WEB_URL>/user/<public_token>
```

### Forward a simple message

**Endpoint:** `/user/<public_token>` (HTTP POST)

Parameters:

 * message
 * _name_
 * _email_
 * _redirect_

`message` is required, all other parameters are optional.

`redirect` can be specified as a URL. Instead of returning a `200 Success` status code, a `302 Redirect` to `redirect` will be issued.

#### Testing from command line

```bash
curl --data "name=Test%20Person&message=Hello" <WEB_URL>/user/<public_token>
```

##### Troubleshooting

If this does not work (an error is returned), then it's likely an issue with your Mailgun setup. First, double check your `MAILGUN_DOMAIN` and `MAILGUN_API_KEY` are correct.

Also, ensure that you've either added your email as an [Authorized Recipient or provided payment information](https://help.mailgun.com/hc/en-us/articles/203068914-What-are-the-differences-between-free-and-paid-accounts) in Mailgun. Regardless, of whether you chose the "Concept" plan or remain on the "Free" (sandboxed) plan, you'll have a quota of emails each month that are 100% free (10,000/month at the time of writing).

#### HTML

A message form for you website would look something like:

```html
<form action="<WEB_URL>/user/<public_token>">
    <div>
        Name: <input name="name" type="text">
    </div>
    <div>
        E-mail: <input name="email" type="text">
    </div>
    <div>
        Message: <textarea name="message" rows="6" cols="120"></textarea>
    </div>
    <div>
        <input name="redirect" type="hidden" value="https://<YOUR_WEBSITE>/<YOUR_POST_SUBMISSION_PAGE>">
        <input type="submit" value="Submit">
    </div>
</form>
```

## Advanced usage: Registered forms

Sometimes we want to do something a bit more advanced than sending a plain-text message to an email address.

Instead we may want our form to:

 * Send emails containing HTML.
 * Send an automated response to the person who submitted the form (i.e. a confirmation email)[*](#auto-response-sandbox).
 * Generate our emails (in particular our automated response) from a template.

In order to achieve this we can register some additional information with the server to make this possible.

<a name="auto-response-sandbox"></a> \* Sending automated responses will almost certainly require that your Mailgun Domain is out of sandbox mode. Otherwise, Mailgun will return an error (and so will fwdform2) whenever we try send an automated response to someone who isn't an authorized recipient.

### Registering a form

You may want to have multiple forms with different behavior all delivered to the one email address (user). As such each fwdform2 user may register multiple forms that will all be delivered to them.

**Endpoint:** `/user/<public_token>/form` (HTTP POST)

Parameters:

 * token
 * subject
 * body
 * _html_body_
 * _response_subject_
 * _response_body_
 * _response_html_body_
 * _response_from_
 * _response_reply_to_

`token` is the user's `private_token`.

`token`, `subject` and `body` are required, all other parameters are optional.

**Note:** To send an automated response, at a minimum a `response_body` must be provided. You cannot provide `response_html_body` on its lonesome, a plain-text body must always be provided.

`subject`, `body`, `html_body`, `response_subject`, `response_body` and `response_html_body` can all be provided as a template, where occurrences of `%parameter%` will be replaced by a parameter in the submitted form.

e.g. If you provide `response_body` as:

> Hi %name%,
>
> Thanks for reaching out. We'll get back to you ASAP.
>
> \- Us

Then in the submitted form include a `name` parameter, the submitter's name will automatically be substituted into the auto-response email.

Returns:

 * form_token

#### Registering a form from command line

```bash
curl --data "token=<private_token>&subject=Just%20saying%20hi&body=Hello%20%25name%25" <WEB_URL>/user/<public_token>/form
```

**Note:** We've URL encoded our spaces and percentage signs as `%20` and `%25` respectively. Web browsers will do this for you automatically, doing this manually is typically only necessary from command line.

### Delete a form

**Endpoint:** `/form/<form_token>` (HTTP DELETE)

Parameters:

 * token

Token is the user's `private_token`. Users can only delete forms that they created.

#### Deleting a form from command line

```bash
curl -X DELETE --data "token=<private_token>" <WEB_URL>/form/<form_token>
```

### Forward a form

**Endpoint:** `/form/<form_token>` (HTTP POST)

Parameters:

* _email_
* _redirect_
* _Any custom parameters you want to use in your templates._

There are no required parameters. However, if you want to send an automated response, an `email` must be provided. 

`redirect` can be specified as a URL. Instead of returning a `200 Success` status code, a `302 Redirect` to `redirect` will be issued.

#### Testing from command line

```bash
curl --data "name=John%20Smith" <WEB_URL>/form/<form_token>
```
