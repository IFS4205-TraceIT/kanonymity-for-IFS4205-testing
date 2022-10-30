import psycopg2
import os
import csv
import pandas as pd
import anonymize
import argparse
from datetime import datetime, date
import sys

# Arguments used by k-anonymity
k = 2
kalgo = "mondrian"
dataset = "traceit"

# Folders used
datafolder = "./data/"
resultfolder = "./results/"

# SQLs files
view_file ="researchdata_view.sql"
researchdb_file = "researchdb.sql"

# Variables used by database
# [ip address, database name, username, password]
maindb = [os.environ['POSTGRES_HOST'],os.environ['POSTGRES_DB'],os.environ['POSTGRES_USER'],os.environ['POSTGRES_PASSWORD'],os.environ['POSTGRES_PORT'],os.environ['POSTGRES_SSL_CERT'],os.environ['POSTGRES_SSL_KEY'],os.environ['POSTGRES_SSL_ROOT_CERT']]
researchdb = [os.environ['POSTGRES_RESEARCH_HOST'],os.environ['POSTGRES_RESEARCH_DB'],os.environ['POSTGRES_RESEARCH_USER'],os.environ['POSTGRES_RESEARCH_PASSWORD'],os.environ['POSTGRES_RESEARCH_PORT'],os.environ['POSTGRES_RESEARCH_SSL_CERT'],os.environ['POSTGRES_RESEARCH_SSL_KEY'],os.environ['POSTGRES_RESEARCH_SSL_ROOT_CERT']]


# Important columns_type = {age, postal, gender}
columns_type = ["age", "gender", "postal", "si", "si", "si", "si", "si", "si"]
columns = ["dob","gender", "postal_code", "list_of_vaccines", "last_close_contact", "last_infected_date", "total_infection", "total_close_contact_as_infected", "total_close_contact_with_infected"]
quasi_identifiers = [0, 1 ,2] # Store them by the array index

def list_to_string(list):
    result = ""
    delim = "/"
    for each in list:
        each = str(each).replace("/","")
        result += (each + delim)
    return result[:-1]

def filter_data(list):
    result = ""
    for each in list:
        if type(each) == type([]):
            each = list_to_string(each)
        each = str(each).replace(";","")
        result += each+";"
    return result[:-1]

def write_to_file(result, file_path):
    with open(file_path, 'w') as f:
        writer = csv.writer(f)
        # write column headers
        writer.writerow([filter_data(columns)])
        for each in result:
            # write data per row
            writer.writerow([filter_data(each)])

def db_export(conn, file_path):
    if file_path == None:
        file_path = datafolder + dataset + "/" + dataset + '.csv'
    cur = conn.cursor()
    sql_file = open(view_file)
    sql_as_string = sql_file.read()
    cur.execute(sql_as_string)
    result = cur.fetchall()
    write_to_file(result, file_path)
    data = pd.DataFrame(result, columns = columns)
    return data

def get_age(data):
    birthDate = datetime.strptime(data, '%Y-%m-%d')
    today = date.today()
    age = today.year - birthDate.year - ((today.month, today.day) < (birthDate.month, birthDate.day))
    return abs(age)

def process_age(data):
    process_result = ""
    process_result += ";" + data[:-3]
    age = get_age(data)
    process_result += ";" + str(age)
    process_result += ";" + str(int(age/10) * 10) + "-" + str(((int(age/10) + 1) * 10)-1)
    return process_result
    


def get_hierarchy(data, datatype):
    data = str(data)
    end = ";*"
    result = data
    if datatype == "age":
        result += process_age(data)
    elif datatype == "postal":
        result += ";" + data[:-1] + "*"
        result += ";" + data[:-2] + "**"
        result += ";" + data[:-3] + "***"
        result += ";" + data[:-4] + "****"
        result += ";" + data[:-5] + "*****"
    elif datatype == "gender":
        pass
    else:
        return None
    return result + end

def generate_hierarchy(data):
    for i in quasi_identifiers:
        with open(datafolder + dataset + "/hierarchies/" + dataset + '_hierarchy_' + columns[i] +'.csv', 'w') as f:
            writer = csv.writer(f)
            for each in data[columns[i]].unique():
                result = get_hierarchy(each, columns_type[i])
                writer.writerow([result])
        

def db_con(dbargs):
    conn = None
    try:
        conn = psycopg2.connect(
            host=dbargs[0],
            database=dbargs[1],
            user=dbargs[2],
            password=dbargs[3],
            port=dbargs[4],
            sslmode="verify-ca",
            sslcert=dbargs[5],
            sslkey=dbargs[6],
            sslrootcert=dbargs[7]
        )
        return conn
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    return None


def clean_db(conn, cur):
    sql_file = open(researchdb_file)
    sql_as_string = sql_file.read()
    cur.execute(sql_as_string)
    conn.commit()

def db_import(conn, file_path):
    if file_path == None:
        file_path = resultfolder + dataset + "/" + kalgo + "/" + dataset + "_anonymized_" + str(k) + ".csv"
    cur = conn.cursor()
    clean_db(conn, cur)

    insert_statement = """
        insert into researchdata
        (dob, gender, postal_code, list_of_vaccines, last_close_contact, last_infected_date, total_infection, total_close_contact_as_infected, total_close_contact_with_infected) 
        values(%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        with open(file_path,'r') as f:
            next(f)
            reader = csv.reader(f)
            for each in reader:
                if(not each):
                    continue
                temp = tuple(each[0].split(";"))
                if(len(temp) != 9):
                    continue
                try:
                    cur.execute(insert_statement,temp)
                    conn.commit()
                except (Exception, psycopg2.DatabaseError) as error:
                    cur.execute("ROLLBACK")
                    conn.commit()
    except IOError:
        print("File not found\n")
        return
            

def get_args(method, kvalue, datafolder_name):
    parser = argparse.ArgumentParser('K-Anonymize')
    parser.add_argument('--method', type=str, default=method,
                        help="K-Anonymity Method")
    parser.add_argument('--k', type=int, default=kvalue,
                        help="K-Anonymity or L-Diversity")
    parser.add_argument('--dataset', type=str, default=datafolder_name,
                        help="Dataset to anonymize")
    return parser.parse_args()

def main():
    conn = db_con(maindb)
    if(conn == None):
        return
    
    # Get data from database into a csv file
    try:
        data = db_export(conn, None)
    except Exception:
        return
    conn.close()

    # Create generalization hierarchy files
    generate_hierarchy(data)
    
    # k-anonymity by kaylode
    global k
    args = get_args(kalgo,k,dataset)
    k = int(args.k)
    anonymize.main(args)
    
    # Gather anonymized data in results and add to research database
    conn = db_con(researchdb)
    db_import(conn, None)
    conn.close()
    

if __name__ == '__main__':
    main()
