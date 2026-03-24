variable "region" {
  default = "us-east-1"
}

variable "vpc_cidr" {
  default = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  default = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  default = "10.0.2.0/24"
}

variable "my_ip" {
  description = "49.204.227.124/32"
}

variable "key_name" {
  description = "mykeypair"
}


# 












# variable "region" {
#   default = "us-east-1"
# }

# variable "vpc_cidr" {
#   default = "10.0.0.0/16"
# }

# variable "public_subnet_cidr" {
#   default = "10.0.1.0/24"
# }

# variable "private_subnet_cidr" {
#   default = "10.0.2.0/24"
# }

# variable "my_ip" {
#   description = "2406:7400:43:f7e3:616b:39e1:ff01:a155"
# }

# variable "key_name" {
#   description = "rajrootkey"
# }