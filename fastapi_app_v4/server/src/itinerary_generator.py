import aiohttp
import asyncio
import datetime
import time
import json
import logging
import os
import requests
import re
import openai

from yelp_restaurants import main

from google.cloud import storage
from dotenv import load_dotenv, find_dotenv
from openai import ChatCompletion

_ = load_dotenv(find_dotenv())
logging.basicConfig(level=logging.INFO)

class ItineraryGenerator:

    def __init__(self):
        self.log_bucket_name = os.getenv("BUCKET_NAME")
        self.feedback_bucket_name = os.getenv("FEEDBACK_BUCKET_NAME")
        self.storage_client = storage.Client()
        self.default_template = self.load_prompt()
        self.prompt = {"role": "system", "content":self.default_template}
        self.selected_llm = None
        self.user_query_template = None
        self.generated_itinerary = None

    def log_llm_response(self, llm, query, itinerary):
        self.selected_llm = llm
        self.user_query_template = query
        self.generated_itinerary = itinerary
        self._upload_to_bucket(self.log_bucket_name, {"id": self._get_unique_id(), "query": query, "llm": llm, "itinerary": itinerary})

    def user_feedback(self, rating, feedback):
        llm, query, itinerary = self.selected_llm, self.user_query_template, self.generated_itinerary
        self._upload_to_bucket(self.feedback_bucket_name,{
            "id": self._get_unique_id(),
            "user_query": query,
            "LLM": llm,
            "itinerary": itinerary,
            "user_rating": rating,
            "user_feedback": feedback
        })

    def _upload_to_bucket(self, bucket_name, data):
        data_str = json.dumps(data)
        bucket = self.storage_client.get_bucket(bucket_name)
        blob_name = f"log_{self._get_unique_id()}_json"
        blob = bucket.blob(blob_name)
        blob.upload_from_string(data_str)

    @staticmethod
    def _get_unique_id():
        return datetime.datetime.now().strftime("%Y%m%d%H%M%S")

    
    @staticmethod
    def load_prompt():
        """
        Define the prompt template for the itinerary planning.
        """
        return """
            You are an expert intelligent and creative AI itinerary planner with extensive knowledge of places worldwide. Your goal is to plan an optimized itinerary for the user based on their specific interests and preferences, geographical proximity, and efficient routes to minimize travel time. To achieve this, follow these instructions:

            1. Suggest atleast 3 activities per day. Each activity should include the name of the place, a brief description, estimated cost, and time to visit the place.
            
            2. Generate a well-structured itinerary including day-to-day activities, timings to visit each location, and estimated costs for the user's reference.

            3. Take into account factors such as geographical proximity between destinations, transportation options, and other logistical considerations when planning the route.
            
            By following these guidelines, you will create a comprehensive and optimized itinerary that meets the user's expectations while ensuring minimal travel time.

            Consider the following example to understand the task better:

            Positive Example:
                Human: Plan a trip to Boston from Oct 20th to Oct 22nd with a budget of $600. Start the itinerary each day from 9 am to 8 pm. 
                AI: {
  "Name": "Boston Exploration",
  "description": "A 3-day immersive experience in the heart of Boston, capturing its historical essence, urban charm, and artistic flair.",
  "budget": "$600",
  "data": [
    {
      "day": 1,
      "day_description": "Historical Exploration",
      "places": [
        {
          "name": "Freedom Trail",
          "description": "A 2.5-mile-long path through downtown Boston that passes by 16 historically significant sites.",
          "time_to_visit": "9:00 - 11:00",
          "budget": "$0"
        },
        {
          "name": "USS Constitution Museum",
          "description": "Explore the history of the world's oldest commissioned warship afloat.",
          "time_to_visit": "11:30 - 13:00",
          "budget": "$10"
        },
        {
          "name": "Faneuil Hall Marketplace",
          "description": "A historic market complex, also known as 'The Cradle of Liberty', offering shopping, dining, and entertainment.",
          "time_to_visit": "14:00 - 17:00",
          "budget": "$50"
        }
      ]
    },
    {
      "day": 2,
      "day_description": "Urban Exploration",
      "places": [
        {
          "name": "Boston Public Garden",
          "description": "A serene landscape with a variety of plants, fountains, and the famous Swan Boats.",
          "time_to_visit": "9:00 - 10:30",
          "budget": "$5"
        },
        {
          "name": "Newbury Street",
          "description": "Boston's premier shopping boulevard known for its many shops, cafes, and historic buildings.",
          "time_to_visit": "11:00 - 14:00",
          "budget": "$100"
        },
        {
          "name": "Skywalk Observatory",
          "description": "Offers the best panoramic views of the Boston skyline from the Prudential Center.",
          "time_to_visit": "15:00 - 17:00",
          "budget": "$20"
        }
      ]
    },
    {
      "day": 3,
      "day_description": "Artistic Getaway",
      "places": [
        {
          "name": "Museum of Fine Arts",
          "description": "One of the most comprehensive art museums in the world with a collection that encompasses nearly 500,000 works of art.",
          "time_to_visit": "9:00 - 12:00",
          "budget": "$25"
        },
        {
          "name": "Isabella Stewart Gardner Museum",
          "description": "An art museum in Boston which houses significant European, Asian, and American art collections.",
          "time_to_visit": "12:30 - 14:30",
          "budget": "$15"
        },
        {
          "name": "Boston Symphony Orchestra",
          "description": "Experience a mesmerizing performance at one of the country's premier orchestras.",
          "time_to_visit": "16:00 - 18:00",
          "budget": "$75"
        }
      ]
    }
  ]
}

            Negative Example:
                Human: Plan a trip to Boston from Oct 20th to Oct 22nd with a budget of $600. Start the itinerary each day from 9 am to 8 pm. 
                AI: {
  "Name": "Boston Misadventure",
  "description": "A 3-day experience in Boston.",
  "budget": "$600",
  "data": [
    {
      "day": 1,
      "day_description": "Relaxing Spa Day",
      "places": [
        {
          "name": "Luxury Spa Boston",
          "description": "A high-end spa offering a range of treatments and relaxation sessions.",
          "time_to_visit": "9:00 - 12:00",
          "budget": "$200"
        },
        {
          "name": "Another Boston Spa",
          "description": "Yet another spa, similar to the first one, offering almost identical treatments.",
          "time_to_visit": "12:30 - 15:30",
          "budget": "$200"
        },
        {
          "name": "Freedom Trail",
          "description": "A 2.5-mile-long path through downtown Boston that passes by 16 historically significant sites. Might be tiring after two spa sessions.",
          "time_to_visit": "16:00 - 18:00",
          "budget": "$0"
        }
      ]
    },
    {
      "day": 2,
      "day_description": "Geographically Inefficient Exploration",
      "places": [
        {
          "name": "Boston Harbor Islands",
          "description": "A group of islands requiring a ferry ride. Offers hiking, picnics, and historical sites.",
          "time_to_visit": "9:00 - 11:00",
          "budget": "$20"
        },
        {
          "name": "Harvard University",
          "description": "Located in Cambridge, it's quite a distance from the harbor. A prestigious institution with historic buildings.",
          "time_to_visit": "12:00 - 14:00",
          "budget": "$0"
        },
        {
          "name": "Franklin Park Zoo",
          "description": "Located even further away, this zoo offers a variety of animals and exhibits.",
          "time_to_visit": "15:00 - 18:00",
          "budget": "$20"
        }
      ]
    },
    {
      "day": 3,
      "day_description": "Random Choices",
      "places": [
        {
          "name": "A Random Coffee Shop",
          "description": "Just a regular coffee shop with nothing special about it.",
          "time_to_visit": "9:00 - 10:00",
          "budget": "$5"
        },
        {
          "name": "Generic Gift Shop",
          "description": "A touristy gift shop selling overpriced souvenirs.",
          "time_to_visit": "10:30 - 12:00",
          "budget": "$50"
        },
        {
          "name": "Some Park",
          "description": "A regular park with a playground and some benches.",
          "time_to_visit": "12:30 - 14:00",
          "budget": "$0"
        }
      ]
    }
  ]
}

        The negative itinerary includes two spas in one day, places that are geographically far apart, and some random choices that might not offer the best experience for a traveler.

            Human:
            AI:
            
            """
    
    @staticmethod
    def load_itinerary_template_json(
            destination, budget, arrival_date, departure_date, start_time, end_time, additional_info, restaurants
    ):
        
        query = f"""
            Be creative. Plan a trip to {destination} from {arrival_date} to {departure_date} with a budget of ${budget}. Start the itinerary each day from {start_time} to {end_time}. Consider additional information regarding {additional_info}, if provided.
        """
        
        template = f"""{query}. 
    Consider budget, timings and requirements. Include estimated cost and timings to visit for each activity.
    Use this restaurants list {restaurants} to suggest atleast one restaurant per day. 
    Structure the itinerary as follows:
    {{"Name":"name of the trip", "description":"description of the entire trip", "budget":"budget of the entire thing", "data": [{{"day":1, "day_description":"Description based on the entire day's places. in a couple of words, for example: `Historical Exploration`, `Spiritual Tour`, `Adventurous Journey`, `Dayout in a beach`,`Urban Exploration`, `Wildlife Safari`,`Relaxing Spa Day`,`Artistic Getaway`, `Romantic Getaway`, `Desert Safari`, `Island Hopping Adventure`",  "places":[{{"name":"Place Name", "description":"Place Description","time_to_visit": "time to visit this place, for example: 9:00 to 10:00", "budget":"cost"}}, {{"name":"Place Name 2", "description":"Place Description 2","time_to_visit": "time to visit this place, for example 10:30 - 13:00", "budget":"cost"}}]}}, {{"day":2, "day_description": "Description based on the entire day's places", "places":[{{"name":"Place Name","description":"Place Description","time_to_visit": "time to visit this place","budget":"cost"}}, {{"name":"Place Name 2", "description":"Place Description 2","time_to_visit": "time to visit this place","budget":"cost"}}]}}]}}
    Note: Do not include any extra information outside this structure."""

        return query, template


    async def fetch_place_details(self, session, place, destination, api_key, SEARCH_URL, DETAILS_URL, PHOTO_URL):

        search_payload = {
            'input': place['name'] + ', ' + destination,
            'inputtype': 'textquery',
            'fields': 'place_id',
            'key': api_key
        }

        async with session.get(SEARCH_URL, params=search_payload) as response:
            search_response = await response.json()
        
        if search_response['candidates']:
            place_id = search_response['candidates'][0]['place_id']
            details_payload = {
                'place_id': place_id,
                'fields': 'name,editorial_summary,geometry,formatted_address,reviews,type,website,formatted_phone_number,price_level,rating,user_ratings_total,photo',
                'key': api_key
            }
            async with session.get(DETAILS_URL, params=details_payload) as response:
                details_response = await response.json()
            place_details = details_response['result']

            place.update({
                'address': place_details.get('formatted_address', ''),
                'latitude': place_details['geometry']['location']['lat'],
                'longitude': place_details['geometry']['location']['lng'],
                'name': place_details.get('name', ''),
                'editorial_summary': place_details.get('editorial_summary', ''),
                'reviews': place_details.get('reviews', []),
                'type': place_details.get('type', ''),
                'website': place_details.get('website', ''),
                'formatted_phone_number': place_details.get('formatted_phone_number', ''),
                'price_level': place_details.get('price_level', ''),
                'rating': place_details.get('rating', ''),
                'user_ratings_total': place_details.get('user_ratings_total', '')
            })

            if 'photos' in place_details:
                photo_reference = place_details['photos'][0]['photo_reference']
                photo_payload = {
                    'maxwidth': 400,
                    'photoreference': photo_reference,
                    'key': api_key
                }
                async with session.get(PHOTO_URL, params=photo_payload) as response:
                    place['photo_url'] = str(response.url)


    async def google_place_details(self, destination, itinerary):
        # Base URLs for Google Places API
        SEARCH_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
        PHOTO_URL = "https://maps.googleapis.com/maps/api/place/photo"
        
        google_api_key = os.getenv("GPLACES_API_KEY")

        # Modified regex to handle both variations
        json_str_match = re.search(r'({+.*}+)', itinerary, re.DOTALL)
        if json_str_match:
            json_str = json_str_match.group(1)
            # Remove any extra curly braces
            while '{{' in json_str and '}}' in json_str:
                json_str = json_str[1:-1]
            trip_data = json.loads(json_str)
        else:
            # Handle the case where the regex doesn't match
            raise ValueError("Invalid JSON format in itinerary")

        async with aiohttp.ClientSession() as session:
            tasks = []
            for day_data in trip_data['data']:
                for place in day_data['places']:
                    task = asyncio.ensure_future(self.fetch_place_details(session, place, destination, google_api_key, SEARCH_URL, DETAILS_URL, PHOTO_URL))
                    tasks.append(task)
            await asyncio.gather(*tasks)

        return trip_data

    
    @staticmethod
    def validate_json_format(new_itinerary):
        """
        Validate if the provided string is in JSON format.
        """
        try:
            json.loads(new_itinerary)
            return True
        except json.JSONDecodeError:
            return False

    
    def handle_invalid_json(self, itinerary):
        """
        Handle the case when the generated itinerary is not in valid JSON format.
        """
        prompt = f"""You are an expert in JSON formatting. Please ensure the following text is in correct and valid JSON format. 
                Complete the following JSON structure to produce a valid JSON structure:
                example: 
                {itinerary}
                Ensure the final output is a well-structured and valid JSON.
            """
        itinerary = ChatCompletion.create(
                            model="gpt-3.5-turbo",
                            messages=[{"role": "user", "content":prompt}],
                            temperature=0
        )
        new_itinerary = itinerary['choices'][0]['message']['content']
        
        return new_itinerary
    
    async def generate_itinerary(self, llm, destination, budget, arrival_date, departure_date, start_time, end_time, additional_info):
        restaurants = main(destination)
        modified_itinerary = None  

        if llm == "Atlas v2":
            user_query, user_query_template = self.load_itinerary_template_json(
            destination, budget, arrival_date, departure_date, start_time, end_time, additional_info, restaurants
        )
            

            openai.api_key = os.getenv("OPENAI_API_KEY")
            conversation = ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "system", "content":self.default_template},
                          {"role": "user", "content":user_query_template}],
                temperature=0.9
            )

            new_itinerary = conversation['choices'][0]['message']['content']
            new_itinerary = re.search(r'\{.*\}', new_itinerary, re.DOTALL).group()
            new_itinerary = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', '', new_itinerary) # Replace invalid backslashes

            # Validate if new_itinerary is in correct JSON format
            if not self.validate_json_format(new_itinerary):
                print("\n ============== Invalid JSON format in itinerary ============== \n")
                new_itinerary = self.handle_invalid_json(itinerary=new_itinerary)
            
            modified_itinerary = await self.google_place_details(destination=destination, itinerary=new_itinerary)
                
            try:
                self.log_llm_response(llm=llm, query=user_query, itinerary=modified_itinerary)
            except Exception as e:
                logging.error(f"Error: {str(e)}")

        return modified_itinerary